from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

from .paths import slugify


SourceType = Literal["book", "article", "web_page", "manual", "curriculum", "pdf", "unknown"]


class SourceMetadata(BaseModel):
    source_id: str
    title: str
    source_type: SourceType = "unknown"
    author_or_publisher: str | None = None
    year: str | None = None
    url: str | None = None
    doi: str | None = None
    file_name: str | None = None

    @classmethod
    def from_path(cls, path: Path) -> SourceMetadata:
        return cls(
            source_id=slugify(path.stem, max_len=80, fallback="source"),
            title=path.stem,
            source_type="pdf" if path.suffix.lower() == ".pdf" else "unknown",
            file_name=path.name,
        )


class SourceManifestEntry(SourceMetadata):
    path: str | None = None

    def matches(self, document_path: Path, base_dir: Path) -> bool:
        document_path = document_path.resolve()
        if self.path:
            manifest_path = (base_dir / self.path).resolve()
            if manifest_path == document_path:
                return True
            if Path(self.path).name == document_path.name:
                return True
        if self.file_name and self.file_name == document_path.name:
            return True
        return False

    def to_metadata(self, document_path: Path) -> SourceMetadata:
        return SourceMetadata(
            source_id=self.source_id,
            title=self.title,
            source_type=self.source_type,
            author_or_publisher=self.author_or_publisher,
            year=self.year,
            url=self.url,
            doi=self.doi,
            file_name=self.file_name or document_path.name,
        )


class SourceManifest(BaseModel):
    schema_version: Literal["1"] = "1"
    sources: list[SourceManifestEntry] = Field(default_factory=list)

    _base_dir: Path = PrivateAttr(default_factory=lambda: Path("."))

    @classmethod
    def load(cls, path: Path) -> SourceManifest:
        manifest_path = Path(path)
        manifest = cls.model_validate(json.loads(manifest_path.read_text()))
        manifest._base_dir = manifest_path.parent.resolve()
        return manifest

    def resolve(self, document_path: Path) -> SourceMetadata:
        for source in self.sources:
            if source.matches(document_path, self._base_dir):
                return source.to_metadata(document_path)
        return SourceMetadata.from_path(document_path)


def discover_source_manifest(path: Path) -> Path | None:
    """Return the conventional source manifest path for a file or directory."""
    base = path if path.is_dir() else path.parent
    for name in ("source-manifest.json", "sources.json"):
        candidate = base / name
        if candidate.exists():
            return candidate
    return None
