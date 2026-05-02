from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from minerva.cli.common import (
    DEFAULT_DB,
    DEFAULT_EMBED,
    DEFAULT_MODEL,
    Exam,
    format_usage,
    resolve_topic_or_exit,
    run_async,
    validate_count,
)
from minerva.console import console
from minerva.curriculum import rematch_questions
from minerva.embed import EmbedClient
from minerva.generation import generate_questions
from minerva.output import load_questionset, save_json
from minerva.quiz import run_quiz


def quiz(
    file: Annotated[Optional[Path], typer.Argument(help="JSON QuestionSet file to quiz from")] = None,
    topic: Annotated[Optional[str], typer.Option(help="Topic: generate questions then quiz")] = None,
    count: Annotated[int, typer.Option("-c", "--count", help="Number of questions to generate", min=1)] = 3,
    model: Annotated[str, typer.Option("-m", "--model", help="LLM model string (provider:name)")] = DEFAULT_MODEL,
    exam: Annotated[Optional[Exam], typer.Option(help="Curriculum exam: 'primary' or 'final'")] = None,
    node: Annotated[Optional[str], typer.Option(help="Exact curriculum node code e.g. 1_GA_P_6")] = None,
    output: Annotated[Optional[Path], typer.Option("-o", "--output", help="Where to save generated JSON")] = None,
    db: Annotated[Path, typer.Option(help="LanceDB path", envvar="LANCEDB_DIR")] = DEFAULT_DB,
    embed_model: Annotated[str, typer.Option(help="Embedding model string")] = DEFAULT_EMBED,
    verbose: Annotated[bool, typer.Option("-v", "--verbose", help="Show retrieval, curriculum, and token details")] = False,
) -> None:
    """Run an interactive terminal quiz."""
    if file:
        try:
            qs = load_questionset(file)
        except Exception as e:
            console.print(f"[red]Could not load '{file}': {e}[/red]")
            raise typer.Exit(1)
        console.print(f"[dim]Loaded {len(qs.questions)} question(s) on '{qs.topic}'[/dim]")
    elif topic or node:
        validate_count(count)
        curriculum_node, exam, topic = resolve_topic_or_exit(exam, node, topic)

        save_dir = output or Path("./output")
        console.print(f"[dim]Questions will be saved to:[/dim] {save_dir}")

        if verbose:
            console.print(f"[dim]LLM model:       {model}[/dim]")
            console.print(f"[dim]Embedding model: {embed_model}[/dim]")
            console.print(f"[dim]DB:              {db}[/dim]")

        with console.status("Loading embedding model…"):
            retriever = EmbedClient(db_path=db, embedding_model=embed_model, verbose=verbose)

        with console.status(f"Generating {count} question(s) on '{topic}'…"):
            qs, _, usage = run_async(
                generate_questions(
                    topic=topic,
                    count=count,
                    model=model,
                    exam=exam,
                    node=curriculum_node,
                    retriever=retriever,
                    verbose=verbose,
                )
            )
        if verbose:
            console.print(f"[dim]{format_usage(usage, label='Generate')}[/dim]")

        with console.status("Matching curriculum nodes…"):
            rematch_questions(qs.questions, exam, db)

        saved = save_json(qs, save_dir)
        console.print(f"[green]Saved:[/green] {saved}")
    else:
        console.print("[red]Provide a JSON file, --topic, or --node.[/red]")
        raise typer.Exit(1)

    run_quiz(qs.questions)
