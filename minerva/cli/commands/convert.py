from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from minerva.cli.common import DEFAULT_DB, DEFAULT_MODEL, Exam, format_usage, save_outputs
from minerva.console import console
from minerva.inputs import read_input_file
from minerva.render import show_question
from minerva.workflows import (
    ConvertQuestionSetRequest,
    WorkflowInputError,
    convert_question_set,
)


def convert(
    input_file: Annotated[Optional[Path], typer.Argument(help="Text, Markdown, or PDF file containing SBA questions")] = None,
    text: Annotated[Optional[str], typer.Option("--text", help="Inline question text to convert")] = None,
    topic: Annotated[Optional[str], typer.Option("--topic", help="Topic label for the output QuestionSet")] = None,
    exam: Annotated[Optional[Exam], typer.Option(help="Exam type: primary_frca or final_frca; primary/final aliases accepted")] = None,
    model: Annotated[str, typer.Option("-m", "--model", help="LLM model string (provider:name)")] = DEFAULT_MODEL,
    output: Annotated[Path, typer.Option("-o", "--output")] = Path("./output"),
    db: Annotated[Path, typer.Option(help="LanceDB path", envvar="LANCEDB_DIR")] = DEFAULT_DB,
    markdown: Annotated[bool, typer.Option(help="Also save a markdown file")] = False,
    verbose: Annotated[bool, typer.Option("-v", "--verbose", help="Show model and token details")] = False,
) -> None:
    """Convert unstructured SBA question text/PDF to structured QuestionSet JSON."""
    if input_file:
        if not input_file.exists():
            console.print(f"[red]File not found: {input_file}[/red]")
            raise typer.Exit(1)
        raw = read_input_file(input_file)
        derived_topic = topic or input_file.stem.replace("_", " ").replace("-", " ").title()
    elif text:
        raw = text
        derived_topic = topic or "Converted Questions"
    else:
        console.print("[red]Provide a file argument or --text.[/red]")
        raise typer.Exit(1)

    if verbose:
        console.print(f"[dim]LLM model:       {model}[/dim]")
        console.print(f"[dim]DB:              {db}[/dim]")
        console.print(f"[dim]Input:           {len(raw):,} chars[/dim]")

    try:
        result = convert_question_set(
            ConvertQuestionSetRequest(
                text=raw,
                topic=derived_topic,
                model=model,
                exam=exam,
                db_path=db,
            )
        )
    except WorkflowInputError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    if verbose:
        console.print(f"[dim]{format_usage(result.usage, label='Convert')}[/dim]")

    qs = result.question_set
    console.print(f"[green]Parsed {len(qs.questions)} question(s)[/green]")
    for q in qs.questions:
        show_question(q, verbose=verbose)

    save_outputs(qs, output, markdown)
