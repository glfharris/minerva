from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from .console import console
from .curriculum import l2_to_cosine

_TABLE_NAME = "documents"
_CHUNK_SIZE = 300      # words per chunk — safely within PubMedBERT's 512 token limit
_CHUNK_OVERLAP = 50    # word overlap between consecutive chunks
_EMBED_BATCH_SIZE = 32 # aligns with sentence-transformers' internal batch size


@lru_cache(maxsize=None)
def _make_embedder(model_string: str):
    """Parse 'provider:model_name' and return a LanceDB embedding function. Cached per model string."""
    import transformers
    transformers.logging.set_verbosity_error()
    from lancedb.embeddings import get_registry
    provider, _, model_name = model_string.partition(":")
    if not model_name:
        raise ValueError(f"Invalid embedding model string: {model_string!r}. Use 'provider:model_name'.")
    return get_registry().get(provider).create(name=model_name)


def _make_chunk_model(embedder):
    """Dynamically create a LanceModel class for the chosen embedder."""
    from lancedb.pydantic import LanceModel, Vector
    ndims = embedder.ndims()

    class DocumentChunk(LanceModel):
        text: str = embedder.SourceField()
        vector: Vector(ndims) = embedder.VectorField()
        source: str
        page: int

    return DocumentChunk


def _clean_text(text: str) -> str:
    """Clean PDF-extracted text: fix hyphenation, normalise whitespace."""
    text = re.sub(r"-\n", "", text)       # rejoin hyphenated line breaks
    text = re.sub(r"\s+", " ", text)      # collapse whitespace/newlines
    return text.strip()


def _chunk_text(text: str) -> list[str]:
    """Split text into overlapping word-based chunks."""
    words = text.split()
    if len(words) <= _CHUNK_SIZE:
        return [text] if words else []

    chunks = []
    start = 0
    while start < len(words):
        end = min(start + _CHUNK_SIZE, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start += _CHUNK_SIZE - _CHUNK_OVERLAP
    return chunks


def _table_to_markdown(data: list[list]) -> str:
    """Convert pdfplumber table data (list of rows) to a markdown table string."""
    # Replace None cells with empty string
    rows = [[str(cell).strip() if cell is not None else "" for cell in row] for row in data]
    # Drop completely empty rows
    rows = [row for row in rows if any(cell for cell in row)]
    if not rows:
        return ""
    header = "| " + " | ".join(rows[0]) + " |"
    separator = "| " + " | ".join("---" for _ in rows[0]) + " |"
    body = "\n".join("| " + " | ".join(row) + " |" for row in rows[1:])
    return "\n".join(filter(None, [header, separator, body]))


def _extract_page(page) -> tuple[str, list[str]]:
    """Extract prose text and tables from a pdfplumber page.

    Returns (prose_text, list_of_markdown_table_strings).
    Tables are extracted from their bounding boxes; prose is extracted
    from the remaining area so table content is not double-counted.
    """
    tables = page.find_tables()
    table_texts = []

    for table in tables:
        data = table.extract()
        if data:
            md = _table_to_markdown(data)
            if md:
                table_texts.append(md)

    # Crop page to exclude table bounding boxes before extracting prose
    prose_page = page
    for table in tables:
        try:
            prose_page = prose_page.outside_bbox(table.bbox)
        except Exception as e:
            console.log(f"[dim]Warning: could not crop table region ({e}), prose may include table text[/dim]")

    prose = prose_page.extract_text() or ""
    return prose, table_texts


class EmbedClient:
    def __init__(
        self,
        db_path: str | Path = "./lancedb",
        embedding_model: str = "sentence-transformers:NeuML/pubmedbert-base-embeddings",
        verbose: bool = False,
    ) -> None:
        import lancedb
        self.db_path = Path(db_path)
        self.verbose = verbose
        self._db = lancedb.connect(str(db_path))
        self._embedder = _make_embedder(embedding_model)
        self._ChunkModel = _make_chunk_model(self._embedder)

        if _TABLE_NAME in self._db.table_names():
            self._table = self._db.open_table(_TABLE_NAME)
        else:
            self._table = self._db.create_table(_TABLE_NAME, schema=self._ChunkModel)

        self._embedded_sources: set[str] = self._load_sources()

    def _load_sources(self) -> set[str]:
        try:
            df = self._table.to_pandas(columns=["source"])
            return set(df["source"].unique())
        except Exception:
            return set()

    def add_pdf(self, path: Path) -> int:
        """Embed a single PDF. Returns the number of chunks added (0 if skipped)."""
        import pdfplumber
        source = str(path.resolve())
        if source in self._embedded_sources:
            if self.verbose:
                console.log(f"[dim]{path.name} — already embedded, skipping[/dim]")
            return 0

        if self.verbose:
            console.log(f"{path.name} — reading…")

        records = []
        empty_pages = 0
        table_count = 0
        with pdfplumber.open(str(path)) as pdf:
            page_count = len(pdf.pages)
            for page_num, page in enumerate(pdf.pages):
                prose, table_texts = _extract_page(page)
                text = _clean_text(prose)
                if not text and not table_texts:
                    empty_pages += 1
                    continue
                for chunk in _chunk_text(text):
                    records.append({"text": chunk, "source": source, "page": page_num})
                for table_md in table_texts:
                    records.append({"text": table_md, "source": source, "page": page_num})
                    table_count += 1

        if not records:
            console.log(f"[yellow]No text extracted from {path.name}[/yellow]")
            return 0

        if self.verbose:
            from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn
            skipped = f", {empty_pages} empty page(s) skipped" if empty_pages else ""
            tables_note = f", {table_count} table(s)" if table_count else ""
            console.log(f"{path.name} — {page_count} page(s){skipped}{tables_note} → {len(records)} chunk(s), embedding…")
            with Progress(
                TextColumn("  [dim]{task.description}[/dim]"),
                BarColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                console=console,
                transient=True,
            ) as progress:
                task = progress.add_task("chunks", total=len(records))
                for i in range(0, len(records), _EMBED_BATCH_SIZE):
                    batch = records[i:i + _EMBED_BATCH_SIZE]
                    self._table.add(batch)
                    progress.advance(task, len(batch))
            console.log(f"[green]{path.name} — done[/green]")
        else:
            self._table.add(records)

        self._embedded_sources.add(source)

        return len(records)

    def add_dir(self, path: Path) -> None:
        from rich.progress import track
        pdfs = list(Path(path).glob("**/*.pdf"))
        if not pdfs:
            console.log(f"[yellow]No PDFs found in {path}[/yellow]")
            return
        console.log(f"Found {len(pdfs)} PDF(s) in {Path(path).name}/")
        total_chunks = 0
        for pdf in track(pdfs, description="Embedding PDFs", disable=self.verbose):
            total_chunks += self.add_pdf(pdf)
        console.log(f"[green]Done[/green] — {total_chunks} chunk(s) added across {len(pdfs)} file(s)")

    def query(self, text: str, n: int = 5, threshold: float = 0.0) -> str:
        try:
            results = self._table.search(text).limit(n).to_pandas()
            if results.empty:
                return ""
            if threshold > 0.0:
                results = results[results["_distance"].apply(
                    lambda d: l2_to_cosine(d) >= threshold
                )]
            if results.empty:
                return ""
            chunks = [
                f"[{Path(row['source']).name}, p.{row['page'] + 1}]\n{row['text']}"
                for _, row in results.iterrows()
            ]
            return "\n\n---\n\n".join(chunks)
        except Exception as e:
            console.log(f"[yellow]RAG query failed: {e}[/yellow]")
            return ""

    def search_docs(self, text: str, n: int = 5):
        """Return raw search results as a pandas DataFrame (for display in match command)."""
        return self._table.search(text).limit(n).to_pandas()

    def reset(self) -> None:
        self._db.drop_table(_TABLE_NAME)
        self._table = self._db.create_table(_TABLE_NAME, schema=self._ChunkModel)
        self._embedded_sources.clear()
        console.log("Embeddings reset")
