from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from minerva.cli.common import DEFAULT_MODEL, format_usage, run_async
from minerva.cli.display import show_critique
from minerva.console import console
from minerva.critique import critique_questions
from minerva.output import load_questionset, save_json


def critique(
    file: Annotated[Path, typer.Argument(help="JSON QuestionSet file to critique")],
    model: Annotated[str, typer.Option("-m", "--model", help="LLM model string (provider:name)")] = DEFAULT_MODEL,
    output: Annotated[Optional[Path], typer.Option("-o", "--output", help="Output path or directory")] = None,
    verbose: Annotated[bool, typer.Option("-v", "--verbose", help="Show diff alongside feedback")] = False,
) -> None:
    """Run a critique pass on a saved QuestionSet JSON file."""
    if verbose:
        console.print(f"[dim]LLM model:       {model}[/dim]")
    try:
        qs = load_questionset(file)
    except Exception as e:
        console.print(f"[red]Could not load '{file}': {e}[/red]")
        raise typer.Exit(1)

    console.print(f"[dim]Loaded {len(qs.questions)} question(s) on '{qs.topic}'[/dim]")

    with console.status("Critiquing questions…"):
        critique_result, critique_usage = run_async(critique_questions(qs, model))

    if verbose:
        console.print(f"[dim]{format_usage(critique_usage, label='Critique')}[/dim]")

    try:
        qs.questions = show_critique(critique_result, qs.questions, show_feedback=True, show_diff=verbose)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    save_path = output or file.with_stem(file.stem + "_critiqued")
    saved = save_json(qs, save_path)
    console.print(f"\n[green]Saved:[/green] {saved}")
