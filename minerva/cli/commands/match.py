from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from minerva.cli.common import DEFAULT_DB, DEFAULT_EMBED, Exam, Source
from minerva.console import console
from minerva.curriculum import (
    _MATCH_THRESHOLD,
    _make_embedder,
    l2_to_cosine,
    load,
    lookup_node,
    node_path,
    search_table,
)
from minerva.embed import EmbedClient
from minerva.similarity import rank_by_similarity


def match(
    topic: Annotated[str, typer.Argument(help="Topic to search for")],
    source: Annotated[Source, typer.Option(help="What to search")] = Source.curriculum,
    exam: Annotated[Exam, typer.Option(help="Curriculum exam (curriculum only)")] = Exam.primary,
    node: Annotated[
        str | None,
        typer.Option(help="Show similarity score for a specific curriculum node code"),
    ] = None,
    top: Annotated[int, typer.Option(help="Number of top matches to show")] = 5,
    db: Annotated[Path, typer.Option(help="LanceDB path", envvar="LANCEDB_DIR")] = DEFAULT_DB,
    verbose: Annotated[
        bool,
        typer.Option("-v", "--verbose", help="Show extra detail per result"),
    ] = False,
) -> None:
    """Search curriculum nodes or embedded documents for a topic."""
    if verbose:
        console.print(f"[dim]Embedding model: {DEFAULT_EMBED}[/dim]")
        console.print(f"[dim]DB:              {db}[/dim]")

    if source == Source.curriculum:
        if node:
            result = lookup_node(exam, node)
            if result is None:
                console.print(f"[red]No curriculum node found with code '{node}'[/red]")
                raise typer.Exit(1)
            target_node, resolved_exam = result
            with console.status("Loading embedding model…") as status:
                embedder = _make_embedder()
                status.update("Computing similarity…")
                score = rank_by_similarity(
                    topic,
                    [target_node],
                    text=lambda n: n.label,
                    embedder=embedder,
                    n=1,
                )[0][0]
            colour = "green" if score >= _MATCH_THRESHOLD else "yellow"
            threshold_note = (
                ""
                if score >= _MATCH_THRESHOLD
                else " [dim](below match threshold)[/dim]"
            )
            path = node_path(load(resolved_exam), target_node.code)  # type: ignore[arg-type]
            breadcrumb = " → ".join(n.label for n in path)
            console.print(f"[bold]{target_node.code}[/bold]  {breadcrumb}")
            console.print(f"Score: [{colour}]{score:.2f}[/{colour}]{threshold_note}")
            return

        with console.status("Loading embedding model…") as status:
            _make_embedder()
            status.update("Searching curriculum…")
            matches = search_table(topic, exam, db_path=db, n=top)  # type: ignore[arg-type]

        root = load(exam)  # type: ignore[arg-type]
        table = Table(show_header=True, header_style="bold")
        table.add_column("Score", width=7)
        table.add_column("Code", width=16)
        table.add_column("Label")
        if verbose:
            table.add_column("Path", style="dim")

        for score, matched_node in matches:
            colour = "green" if score >= 0.4 else "yellow"
            row = [f"[{colour}]{score:.2f}[/{colour}]", matched_node.code, matched_node.label]
            if verbose:
                ancestors = node_path(root, matched_node.code)[:-1]
                row.append(" > ".join(n.label for n in ancestors) if ancestors else "")
            table.add_row(*row)

        console.print(table)

    elif source == Source.docs:
        with console.status("Loading embedding model…") as status:
            client = EmbedClient(db_path=db)
            status.update("Searching documents…")
            results = client.search_docs(topic, n=top)

        if results.empty:
            console.print("[yellow]No results found — have you embedded any documents?[/yellow]")
            return

        snippet_len = 300 if verbose else 120
        table = Table(show_header=True, header_style="bold")
        table.add_column("Score", width=7)
        table.add_column("Source")
        table.add_column("Page", width=6)
        table.add_column("Text")

        for _, row in results.iterrows():
            d = float(row["_distance"])
            score = l2_to_cosine(d)
            source_name = str(row["source"]) if verbose else Path(row["source"]).name
            snippet = row["text"][:snippet_len].replace("\n", " ")
            colour = "green" if score >= 0.4 else "yellow"
            table.add_row(
                f"[{colour}]{score:.2f}[/{colour}]",
                source_name,
                str(int(row["page"])),
                snippet,
            )

        console.print(table)
