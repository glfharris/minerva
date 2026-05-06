from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from minerva.cli.common import DEFAULT_DB, DEFAULT_EMBED
from minerva.console import console
from minerva.embed import EmbedClient
from minerva.source_manifest import SourceManifest, discover_source_manifest


def embed(
    path: Annotated[Path, typer.Argument(help="Document file or directory to embed")],
    reset: Annotated[bool, typer.Option(help="Drop existing embeddings first")] = False,
    model: Annotated[str, typer.Option(help="Embedding model string")] = DEFAULT_EMBED,
    db: Annotated[Path, typer.Option(help="LanceDB path", envvar="LANCEDB_DIR")] = DEFAULT_DB,
    manifest: Annotated[Path | None, typer.Option(help="Source manifest JSON path")] = None,
    verbose: Annotated[bool, typer.Option("-v", "--verbose", help="Show per-file chunk counts")] = False,
) -> None:
    """Embed documents (PDF/EPUB) into the vector store."""
    if verbose:
        console.print(f"[dim]Embedding model: {model}[/dim]")
        console.print(f"[dim]DB:              {db}[/dim]")

    manifest_path = manifest or discover_source_manifest(path)
    source_manifest = SourceManifest.load(manifest_path) if manifest_path else None
    if verbose and manifest_path:
        console.print(f"[dim]Source manifest: {manifest_path}[/dim]")

    with console.status("Loading embedding model…"):
        client = EmbedClient(
            db_path=db,
            embedding_model=model,
            source_manifest=source_manifest,
            verbose=verbose,
        )

    if reset:
        client.reset()

    if path.is_dir():
        client.add_dir(path)
    elif path.is_file():
        n = client.add_document(path)
        if n:
            console.print(f"[green]Embedded {n} chunk(s) from {path.name}[/green]")
    else:
        console.print(f"[red]Path not found: {path}[/red]")
        raise typer.Exit(1)
