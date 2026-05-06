from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from pydantic_ai.messages import ModelMessagesTypeAdapter

from minerva.cli.common import (
    DEFAULT_DB,
    DEFAULT_EMBED,
    DEFAULT_MODEL,
    Exam,
    format_usage,
    save_outputs,
    show_generation_plan,
    show_critique,
)
from minerva.console import console
from minerva.paths import slugify
from minerva.render import show_question
from minerva.workflows import (
    CreateQuestionSetRequest,
    WorkflowInputError,
    create_question_set,
)


def create(
    topic: Annotated[Optional[str], typer.Argument(help="Question topic (omit to derive from --node label)")] = None,
    count: Annotated[int, typer.Option("-c", "--count", help="Number of questions", min=1)] = 1,
    model: Annotated[str, typer.Option("-m", "--model", help="LLM model string (provider:name)")] = DEFAULT_MODEL,
    exam: Annotated[Optional[Exam], typer.Option(help="Curriculum exam: primary_frca or final_frca; primary/final aliases accepted")] = None,
    node: Annotated[Optional[str], typer.Option(help="Exact curriculum node code e.g. 1_GA_P_6")] = None,
    output: Annotated[Path, typer.Option("-o", "--output", help="Output directory for JSON + markdown")] = Path("./output"),
    db: Annotated[Path, typer.Option(help="LanceDB path", envvar="LANCEDB_DIR")] = DEFAULT_DB,
    embed_model: Annotated[str, typer.Option(help="Embedding model string")] = DEFAULT_EMBED,
    verbose: Annotated[bool, typer.Option("-v", "--verbose", help="Show retrieval, curriculum, and token details")] = False,
    markdown: Annotated[bool, typer.Option(help="Also save a markdown file alongside the JSON")] = False,
    save_example: Annotated[bool, typer.Option(help="Save this run as a few-shot example")] = False,
    critique: Annotated[bool, typer.Option("--critique", help="Run a self-critique pass to improve questions")] = False,
    pin: Annotated[bool, typer.Option("--pin", help="Pin all questions to the specified node; do not distribute to children")] = False,
) -> None:
    """Generate SBA questions on a topic."""
    if verbose:
        console.print(f"[dim]LLM model:       {model}[/dim]")
        console.print(f"[dim]Embedding model: {embed_model}[/dim]")
        console.print(f"[dim]DB:              {db}[/dim]")

    request = CreateQuestionSetRequest(
        topic=topic,
        count=count,
        model=model,
        exam=exam,
        node_code=node,
        db_path=db,
        embedding_model=embed_model,
        verbose=verbose,
        critique=critique,
        pin=pin,
    )
    try:
        result = create_question_set(
            request,
            revise_questions=(
                lambda critique_result, original_questions: show_critique(
                    critique_result,
                    original_questions,
                    show_feedback=verbose,
                    show_diff=verbose,
                )
            ),
            report_generation_plan=show_generation_plan,
            report_no_confident_match=lambda matched_topic: console.print(
                f"[yellow]No confident curriculum match for '{matched_topic}' — generating without curriculum context.[/yellow]"
            ),
        )
    except WorkflowInputError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    qs = result.question_set
    if verbose:
        for i, usage_i in enumerate(result.generation_usages, 1):
            if len(result.generation_usages) > 1:
                console.print(f"[dim]  Q{i}: {format_usage(usage_i)}[/dim]")
        label = "Total" if len(result.generation_usages) > 1 else "Generate"
        console.print(f"[dim]{format_usage(result.usage, label=label)}[/dim]")
        if result.critique_usage:
            console.print(f"[dim]{format_usage(result.critique_usage, label='Critique')}[/dim]")

    for q in qs.questions:
        show_question(q, verbose=verbose)

    save_outputs(qs, output, markdown)

    if save_example:
        history_dir = Path("examples/histories")
        history_dir.mkdir(parents=True, exist_ok=True)
        dest = history_dir / f"{slugify(qs.topic, fallback='example')}.json"
        dest.write_bytes(ModelMessagesTypeAdapter.dump_json(result.messages))
        console.print(f"[green]Saved example:[/green] {dest}")
