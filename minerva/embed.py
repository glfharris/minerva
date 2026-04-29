from __future__ import annotations

from pathlib import Path

import lancedb
from lancedb.embeddings import get_registry
from lancedb.pydantic import LanceModel, Vector
from pypdf import PdfReader
from rich.progress import track

from .console import console

_TABLE_NAME = "documents"


def _make_embedder(model_string: str):
    """Parse 'provider:model_name' and return a LanceDB embedding function."""
    provider, _, model_name = model_string.partition(":")
    if not model_name:
        raise ValueError(f"Invalid embedding model string: {model_string!r}. Use 'provider:model_name'.")
    return get_registry().get(provider).create(name=model_name)


def _make_chunk_model(embedder):
    """Dynamically create a LanceModel class for the chosen embedder."""
    ndims = embedder.ndims()

    class DocumentChunk(LanceModel):
        text: str = embedder.SourceField()
        vector: Vector(ndims) = embedder.VectorField()
        source: str
        page: int

    return DocumentChunk


class EmbedClient:
    def __init__(
        self,
        db_path: str | Path = "./lancedb",
        embedding_model: str = "openai:text-embedding-3-small",
    ) -> None:
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
            df = self._table.to_pandas()
            return set(df["source"].unique())
        except Exception:
            return set()

    def add_pdf(self, path: Path) -> None:
        source = str(path.resolve())
        if source in self._embedded_sources:
            console.log(f"Already embedded: {path.name} — skipping")
            return

        reader = PdfReader(str(path))
        records = []
        for page_num, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            text = text.strip()
            if text:
                records.append({"text": text, "source": source, "page": page_num})

        if not records:
            console.log(f"No text extracted from {path.name}")
            return

        self._table.add(records)
        self._embedded_sources.add(source)
        console.log(f"Embedded {len(records)} page(s) from {path.name}")

    def add_dir(self, path: Path) -> None:
        pdfs = list(Path(path).glob("**/*.pdf"))
        if not pdfs:
            console.log(f"No PDFs found in {path}")
            return
        console.log(f"Found {len(pdfs)} PDF(s)")
        for pdf in track(pdfs, description="Embedding PDFs"):
            self.add_pdf(pdf)

    def query(self, text: str, n: int = 5) -> str:
        try:
            results = self._table.search(text).limit(n).to_pandas()
            if results.empty:
                return ""
            chunks = results["text"].tolist()
            return "\n\n---\n\n".join(chunks)
        except Exception:
            return ""

    def reset(self) -> None:
        self._db.drop_table(_TABLE_NAME)
        self._table = self._db.create_table(_TABLE_NAME, schema=self._ChunkModel)
        self._embedded_sources.clear()
        console.log("Embeddings reset")
