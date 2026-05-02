from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from minerva.cli.common import DEFAULT_DB, DEFAULT_EMBED
from minerva.console import console
from minerva.embed import EmbedClient


def embed(
    path: Annotated[Path, typer.Argument(help="PDF file or directory to embed")],
    reset: Annotated[bool, typer.Option(help="Drop existing embeddings first")] = False,
    model: Annotated[str, typer.Option(help="Embedding model string")] = DEFAULT_EMBED,
    db: Annotated[Path, typer.Option(help="LanceDB path", envvar="LANCEDB_DIR")] = DEFAULT_DB,
    verbose: Annotated[bool, typer.Option("-v", "--verbose", help="Show per-file chunk counts")] = False,
) -> None:
    """Embed PDF documents into the vector store."""
    if verbose:
        console.print(f"[dim]Embedding model: {model}[/dim]")
        console.print(f"[dim]DB:              {db}[/dim]")

    with console.status("Loading embedding model…"):
        client = EmbedClient(db_path=db, embedding_model=model, verbose=verbose)

    if reset:
        client.reset()

    if path.is_dir():
        client.add_dir(path)
    elif path.is_file():
        n = client.add_pdf(path)
        if n:
            console.print(f"[green]Embedded {n} chunk(s) from {path.name}[/green]")
    else:
        console.print(f"[red]Path not found: {path}[/red]")
        raise typer.Exit(1)
