from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from .console import console
from .curriculum import l2_to_cosine
from .source_manifest import SourceManifest, SourceMetadata

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
        source_id: str
        source_title: str
        source_type: str
        source_author_or_publisher: str | None = None
        source_year: str | None = None
        source_url: str | None = None
        source_doi: str | None = None
        source_file_name: str | None = None

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


def _records_from_sections(
    sections: list[tuple[int, str, list[str]]], source: str, metadata: SourceMetadata | None = None
) -> tuple[list[dict], int]:
    """Convert extracted sections to embedding records.

    Returns (records, table_count) where each record is
    {"text": ..., "source": ..., "page": ..., source metadata...}.
    """
    metadata = metadata or SourceMetadata.from_path(Path(source))
    source_fields = {
        "source": source,
        "source_id": metadata.source_id,
        "source_title": metadata.title,
        "source_type": metadata.source_type,
        "source_author_or_publisher": metadata.author_or_publisher,
        "source_year": metadata.year,
        "source_url": metadata.url,
        "source_doi": metadata.doi,
        "source_file_name": metadata.file_name,
    }
    records = []
    table_count = 0
    for section_index, prose, table_texts in sections:
        text = _clean_text(prose)
        for chunk in _chunk_text(text):
            records.append({"text": chunk, "page": section_index, **source_fields})
        for table_md in table_texts:
            records.append({"text": table_md, "page": section_index, **source_fields})
            table_count += 1
    return records, table_count


class EmbedClient:
    def __init__(
        self,
        db_path: str | Path = "./lancedb",
        embedding_model: str = "sentence-transformers:NeuML/pubmedbert-base-embeddings",
        source_manifest: SourceManifest | None = None,
        verbose: bool = False,
    ) -> None:
        import lancedb
        self.db_path = Path(db_path)
        self.verbose = verbose
        self.source_manifest = source_manifest
        self._db = lancedb.connect(str(db_path))
        self._embedder = _make_embedder(embedding_model)
        self._ChunkModel = _make_chunk_model(self._embedder)

        if _TABLE_NAME in self._db.table_names():
            self._table = self._db.open_table(_TABLE_NAME)
        else:
            self._table = self._db.create_table(_TABLE_NAME, schema=self._ChunkModel)

        self._stores_source_metadata = _table_has_column(self._table, "source_id")
        self._embedded_sources: set[str] = self._load_sources()

    def _load_sources(self) -> set[str]:
        try:
            df = self._table.to_pandas()
            return set(df["source"].unique())
        except Exception as e:
            console.log(f"[yellow]Warning: could not read existing sources from table ({e}). Idempotency check disabled.[/yellow]")
            return set()

    def add_document(self, path: Path, source_manifest: SourceManifest | None = None) -> int:
        """Embed a single document (PDF or EPUB). Returns the number of chunks added (0 if skipped)."""
        from .inputs import extract_sections

        manifest = source_manifest or self.source_manifest
        metadata = manifest.resolve(path) if manifest else SourceMetadata.from_path(path)
        source = str(path.resolve())
        if source in self._embedded_sources:
            if self.verbose:
                console.log(f"[dim]{path.name} — already embedded, skipping[/dim]")
            return 0

        if self.verbose:
            console.log(f"{path.name} — reading…")

        sections = extract_sections(path)
        records, table_count = _records_from_sections(sections, source, metadata)

        if manifest and not self._stores_source_metadata:
            raise RuntimeError(
                "Existing documents table does not store source metadata. "
                "Run embed with --reset to rebuild embeddings with the source manifest."
            )
        if not self._stores_source_metadata:
            records = [_without_source_metadata(record) for record in records]

        if not records:
            console.log(f"[yellow]No text extracted from {path.name}[/yellow]")
            return 0

        if self.verbose:
            from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn
            section_count = len(sections)
            empty_sections = section_count - len([s for s in sections if _clean_text(s[1]) or s[2]])
            skipped = f", {empty_sections} empty section(s) skipped" if empty_sections else ""
            tables_note = f", {table_count} table(s)" if table_count else ""
            console.log(f"{path.name} — {section_count} section(s){skipped}{tables_note} → {len(records)} chunk(s), embedding…")
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

    def add_dir(self, path: Path, source_manifest: SourceManifest | None = None) -> None:
        from rich.progress import track
        docs = sorted(
            list(Path(path).glob("**/*.pdf")) + list(Path(path).glob("**/*.epub"))
        )
        if not docs:
            console.log(f"[yellow]No documents found in {path}[/yellow]")
            return
        console.log(f"Found {len(docs)} document(s) in {Path(path).name}/")
        total_chunks = 0
        for doc in track(docs, description="Embedding documents", disable=self.verbose):
            total_chunks += self.add_document(doc, source_manifest=source_manifest)
        console.log(f"[green]Done[/green] — {total_chunks} chunk(s) added across {len(docs)} file(s)")

    def _source_label(self, row) -> str:
        title = _row_value(row, "source_title")
        source_id = _row_value(row, "source_id")
        source_name = title or Path(row["source"]).name
        return f"{source_id}: {source_name}" if source_id else source_name

    def query(self, text: str, n: int = 5, threshold: float = 0.0) -> str:
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
            f"[{self._source_label(row)}, p.{row['page'] + 1}]\n{row['text']}"
            for _, row in results.iterrows()
        ]
        return "\n\n---\n\n".join(chunks)

    def search_docs(self, text: str, n: int = 5):
        """Return raw search results as a pandas DataFrame (for display in match command)."""
        return self._table.search(text).limit(n).to_pandas()

    def reset(self) -> None:
        self._db.drop_table(_TABLE_NAME)
        self._table = self._db.create_table(_TABLE_NAME, schema=self._ChunkModel)
        self._stores_source_metadata = True
        self._embedded_sources.clear()
        console.log("Embeddings reset")


def _row_value(row, key: str):
    try:
        value = row[key]
    except KeyError:
        return None
    return None if value != value else value


def _table_has_column(table, column: str) -> bool:
    try:
        return column in table.schema.names
    except Exception:
        return False


def _without_source_metadata(record: dict) -> dict:
    return {
        key: value
        for key, value in record.items()
        if not key.startswith("source_")
    }
