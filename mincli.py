#! uv run
from __future__ import annotations

import asyncio
from difflib import unified_diff
from enum import StrEnum
import logging
import os
from pathlib import Path
from typing import Annotated, Optional
import warnings

# Suppress noisy third-party output before any imports trigger them
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("transformers").setLevel(logging.WARNING)
logging.getLogger("statsmodels").setLevel(logging.WARNING)
warnings.filterwarnings("ignore", module="statsmodels")

import typer
from dotenv import load_dotenv
from rich.table import Table

from minerva.agent import Deps, critique_questions, load_example_messages, make_agent
from pydantic_ai.usage import Usage
from minerva.console import console
from minerva.curriculum import EMBED_MODEL, l2_to_cosine, load, node_path, search_table
from minerva.embed import EmbedClient
from minerva.models import CurriculumNode, QuestionSet
from minerva.output import save_json, save_markdown
from minerva.quiz import run_quiz

load_dotenv()

app = typer.Typer(no_args_is_help=True)


class Exam(StrEnum):
    primary = "primary"
    final = "final"


class Source(StrEnum):
    curriculum = "curriculum"
    docs = "docs"

_DEFAULT_MODEL = os.environ.get("MINERVA_MODEL", "openai:gpt-4o")
_DEFAULT_EMBED = f"sentence-transformers:{EMBED_MODEL}"
_DEFAULT_DB = Path(os.environ.get("LANCEDB_DIR", "./lancedb"))


# (input $/1M tokens, output $/1M tokens)
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    "openai:gpt-5.4-mini":                 (0.75,   4.50),
    "openai:gpt-4o":                       (2.50,  10.00),
    "openai:gpt-4o-mini":                  (0.15,   0.60),
    "openai:o1":                           (15.00,  60.00),
    "anthropic:claude-opus-4-6":           (5.00,   25.00),
    "anthropic:claude-sonnet-4-6":         (3.00,   15.00),
    "anthropic:claude-haiku-4-5-20251001": (0.80,    4.00),
}


def _format_usage(usage: Usage, model: str, label: str = "Usage") -> str:
    req = usage.input_tokens or 0
    resp = usage.output_tokens or 0
    total = usage.total_tokens or (req + resp)
    parts = [f"{label}: {req:,} in / {resp:,} out / {total:,} total tokens"]
    if model in _MODEL_PRICING:
        in_price, out_price = _MODEL_PRICING[model]
        cost = (req * in_price + resp * out_price) / 1_000_000
        parts.append(f"≈ ${cost:.4f}")
    return "  ".join(parts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _show_critique(critique_result, original_questions: list, show_feedback: bool, show_diff: bool) -> list:
    """Display critique feedback and/or diff, then return the revised questions."""
    revised = []
    if show_feedback:
        console.rule("[bold]Critique feedback")

    for i, (cq, original) in enumerate(zip(critique_result.critiqued, original_questions), 1):
        revised.append(cq.question)

        if show_feedback:
            console.print(f"[bold]Q{i}:[/bold] [dim]{cq.feedback}[/dim]")

        if show_diff:
            orig_lines = original.to_md().splitlines(keepends=True)
            new_lines = cq.question.to_md().splitlines(keepends=True)
            diff = list(unified_diff(orig_lines, new_lines, lineterm=""))
            if diff:
                for line in diff[2:]:  # skip --- +++ header
                    if line.startswith("+"):
                        console.print(f"[green]{line.rstrip()}[/green]", highlight=False)
                    elif line.startswith("-"):
                        console.print(f"[red]{line.rstrip()}[/red]", highlight=False)
                    elif line.startswith("@"):
                        console.print(f"[dim]{line.rstrip()}[/dim]", highlight=False)

    return revised


def _lookup_node(exam: Exam, code: str) -> CurriculumNode | None:
    """Look up a curriculum node by exact code."""
    root = load(exam)  # type: ignore[arg-type]
    path = node_path(root, code)
    if not path:
        console.print(f"[red]No curriculum node found with code '{code}'[/red]")
        return None
    return path[-1]


async def _generate(
    topic: str,
    count: int,
    model: str,
    exam: str | None,
    node: CurriculumNode | None,
    retriever: EmbedClient,
    verbose: bool = False,
) -> tuple[QuestionSet, list, Usage]:
    curriculum_path = node_path(load(exam), node.code) if (node and exam) else []  # type: ignore[arg-type]
    deps = Deps(
        retriever=retriever,
        curriculum_path=curriculum_path,
        verbose=verbose,
        exam=None if node else exam,  # only enable match_curriculum tool when no explicit node
        db_path=retriever.db_path,
    )

    prompt = (
        f"Write {count} dissimilar SBA question(s) on: {topic!r}.\n\n"
        "Each question should test application of knowledge, not simple recall — "
        "a candidate should need to reason from principles rather than just retrieve a fact. "
        "Use the retrieve tool to find relevant reference material before writing. "
        "Return the result as a QuestionSet."
    )

    ag = make_agent(model)
    example_messages = load_example_messages()
    result = await ag.run(prompt, deps=deps, message_history=example_messages)
    qs = result.output
    qs.topic = topic
    qs.exam = exam
    qs.model = model
    if node:
        qs.curriculum_node_code = node.code
    return qs, result.all_messages(), result.usage()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.command()
def match(
    topic: Annotated[str, typer.Argument(help="Topic to search for")],
    source: Annotated[Source, typer.Option(help="What to search")] = Source.curriculum,
    exam: Annotated[Exam, typer.Option(help="Curriculum exam (curriculum only)")] = Exam.primary,
    top: Annotated[int, typer.Option(help="Number of top matches to show")] = 5,
    db: Annotated[Path, typer.Option(help="LanceDB path", envvar="LANCEDB_DIR")] = _DEFAULT_DB,
) -> None:
    """Search curriculum nodes or embedded documents for a topic."""
    if source == Source.curriculum:
        with console.status("Searching curriculum…"):
            matches = search_table(topic, exam, db_path=db, n=top)  # type: ignore[arg-type]

        table = Table(show_header=True, header_style="bold")
        table.add_column("Score", width=7)
        table.add_column("Code", width=16)
        table.add_column("Label")

        for score, node in matches:
            colour = "green" if score >= 0.4 else "yellow"
            table.add_row(f"[{colour}]{score:.2f}[/{colour}]", node.code, node.label)

        console.print(table)

    elif source == Source.docs:
        with console.status("Searching documents…"):
            client = EmbedClient(db_path=db)
            results = client.search_docs(topic, n=top)

        if results.empty:
            console.print("[yellow]No results found — have you embedded any documents?[/yellow]")
            return

        table = Table(show_header=True, header_style="bold")
        table.add_column("Score", width=7)
        table.add_column("Source")
        table.add_column("Page", width=6)
        table.add_column("Text")

        for _, row in results.iterrows():
            d = float(row["_distance"])
            score = l2_to_cosine(d)
            source_name = Path(row["source"]).name
            snippet = row["text"][:120].replace("\n", " ")
            colour = "green" if score >= 0.4 else "yellow"
            table.add_row(f"[{colour}]{score:.2f}[/{colour}]", source_name, str(int(row["page"])), snippet)

        console.print(table)


@app.command()
def create(
    topic: Annotated[Optional[str], typer.Argument(help="Question topic (omit to derive from --node label)")] = None,
    count: Annotated[int, typer.Option("-c", "--count", help="Number of questions")] = 1,
    model: Annotated[str, typer.Option("-m", "--model", help="LLM model string (provider:name)")] = _DEFAULT_MODEL,
    exam: Annotated[Optional[Exam], typer.Option(help="Curriculum exam: 'primary' or 'final'")] = None,
    node: Annotated[Optional[str], typer.Option(help="Exact curriculum node code e.g. 1_GA_P_6")] = None,
    output: Annotated[Path, typer.Option("-o", "--output", help="Output directory for JSON + markdown")] = Path("./output"),
    db: Annotated[Path, typer.Option(help="LanceDB path", envvar="LANCEDB_DIR")] = _DEFAULT_DB,
    embed_model: Annotated[str, typer.Option(help="Embedding model string")] = _DEFAULT_EMBED,
    verbose: Annotated[bool, typer.Option("-v", "--verbose", help="Show retrieval details")] = False,
    markdown: Annotated[bool, typer.Option(help="Also save a markdown file alongside the JSON")] = False,
    save_example: Annotated[bool, typer.Option(help="Save this run as a few-shot example")] = False,
    critique: Annotated[bool, typer.Option("--critique", help="Run a self-critique pass to improve questions")] = False,
) -> None:
    """Generate SBA questions on a topic."""
    curriculum_node = _lookup_node(exam, node) if (exam and node) else None

    if not topic:
        if curriculum_node:
            topic = curriculum_node.label
        else:
            console.print("[red]Provide a topic or use --exam and --node together.[/red]")
            raise typer.Exit(1)

    if verbose:
        console.print(f"[dim]LLM model:       {model}[/dim]")
        console.print(f"[dim]Embedding model: {embed_model}[/dim]")

    with console.status("Loading embedding model…"):
        retriever = EmbedClient(db_path=db, embedding_model=embed_model)

    with console.status(f"Generating {count} question(s) on '{topic}'…"):
        qs, messages, usage = asyncio.run(
            _generate(
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
        console.print(f"[dim]{_format_usage(usage, model, label='Generate')}[/dim]")

    if critique:
        with console.status("Critiquing questions…"):
            critique_result, critique_usage = asyncio.run(critique_questions(qs, model))
        if verbose:
            console.print(f"[dim]{_format_usage(critique_usage, model, label='Critique')}[/dim]")
        qs.questions = _show_critique(critique_result, qs.questions, show_feedback=verbose, show_diff=verbose)

    for q in qs.questions:
        q.show()

    j = save_json(qs, output)
    console.print(f"\n[green]Saved:[/green] {j}")
    if markdown:
        m = save_markdown(qs, output)
        console.print(f"[green]Saved:[/green] {m}")

    if save_example:
        from pydantic_ai.messages import ModelMessagesTypeAdapter
        history_dir = Path("examples/histories")
        history_dir.mkdir(parents=True, exist_ok=True)
        slug = topic.lower().replace(" ", "_")
        dest = history_dir / f"{slug}.json"
        dest.write_bytes(ModelMessagesTypeAdapter.dump_json(messages))
        console.print(f"[green]Saved example:[/green] {dest}")


@app.command()
def embed(
    path: Annotated[Path, typer.Argument(help="PDF file or directory to embed")],
    reset: Annotated[bool, typer.Option(help="Drop existing embeddings first")] = False,
    model: Annotated[str, typer.Option(help="Embedding model string")] = _DEFAULT_EMBED,
    db: Annotated[Path, typer.Option(help="LanceDB path", envvar="LANCEDB_DIR")] = _DEFAULT_DB,
    verbose: Annotated[bool, typer.Option("-v", "--verbose", help="Show per-file chunk counts")] = False,
) -> None:
    """Embed PDF documents into the vector store."""
    if verbose:
        console.print(f"[dim]Embedding model: {model}[/dim]")
        console.print(f"[dim]LanceDB path:     {db}[/dim]")

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


@app.command()
def quiz(
    file: Annotated[Optional[Path], typer.Argument(help="JSON QuestionSet file to quiz from")] = None,
    topic: Annotated[Optional[str], typer.Option(help="Topic: generate questions then quiz")] = None,
    count: Annotated[int, typer.Option("-c", "--count", help="Questions to generate")] = 3,
    model: Annotated[str, typer.Option("-m", "--model", help="LLM model string")] = _DEFAULT_MODEL,
    exam: Annotated[Optional[Exam], typer.Option(help="Curriculum exam: 'primary' or 'final'")] = None,
    node: Annotated[Optional[str], typer.Option(help="Exact curriculum node code e.g. 1_GA_P_6")] = None,
    output: Annotated[Optional[Path], typer.Option("-o", "--output", help="Where to save generated JSON")] = None,
    db: Annotated[Path, typer.Option(help="LanceDB path", envvar="LANCEDB_DIR")] = _DEFAULT_DB,
    embed_model: Annotated[str, typer.Option(help="Embedding model string")] = _DEFAULT_EMBED,
    verbose: Annotated[bool, typer.Option("-v", "--verbose", help="Show retrieval details")] = False,
) -> None:
    """Run an interactive terminal quiz."""
    if file:
        try:
            qs = QuestionSet.model_validate_json(file.read_text())
        except Exception as e:
            console.print(f"[red]Could not load '{file}': {e}[/red]")
            raise typer.Exit(1)
        console.print(f"[dim]Loaded {len(qs.questions)} question(s) on '{qs.topic}'[/dim]")
    elif topic:
        curriculum_node = _lookup_node(exam, node) if (exam and node) else None

        save_dir = output or Path("./output")
        console.print(f"[dim]Questions will be saved to:[/dim] {save_dir}")

        if verbose:
            console.print(f"[dim]LLM model:       {model}[/dim]")
            console.print(f"[dim]Embedding model: {embed_model}[/dim]")

        with console.status("Loading embedding model…"):
            retriever = EmbedClient(db_path=db, embedding_model=embed_model, verbose=verbose)

        with console.status(f"Generating {count} question(s) on '{topic}'…"):
            qs, _, usage = asyncio.run(
                _generate(
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
            console.print(f"[dim]{_format_usage(usage, model, label='Generate')}[/dim]")
        saved = save_json(qs, save_dir)
        console.print(f"[green]Saved:[/green] {saved}")
    else:
        console.print("[red]Provide a JSON file or use --topic to generate questions.[/red]")
        raise typer.Exit(1)

    run_quiz(qs.questions)


@app.command()
def critique(
    file: Annotated[Path, typer.Argument(help="JSON QuestionSet file to critique")],
    model: Annotated[str, typer.Option("-m", "--model", help="LLM model string (provider:name)")] = _DEFAULT_MODEL,
    output: Annotated[Optional[Path], typer.Option("-o", "--output", help="Output path or directory")] = None,
    verbose: Annotated[bool, typer.Option("-v", "--verbose", help="Show diff alongside feedback")] = False,
) -> None:
    """Run a critique pass on a saved QuestionSet JSON file."""
    try:
        qs = QuestionSet.model_validate_json(file.read_text())
    except Exception as e:
        console.print(f"[red]Could not load '{file}': {e}[/red]")
        raise typer.Exit(1)

    console.print(f"[dim]Loaded {len(qs.questions)} question(s) on '{qs.topic}'[/dim]")

    with console.status("Critiquing questions…"):
        critique_result, critique_usage = asyncio.run(critique_questions(qs, model))

    if verbose:
        console.print(f"[dim]{_format_usage(critique_usage, model, label='Critique')}[/dim]")

    qs.questions = _show_critique(critique_result, qs.questions, show_feedback=True, show_diff=verbose)

    save_path = output or file.with_stem(file.stem + "_critiqued")
    j = save_json(qs, save_path)
    console.print(f"\n[green]Saved:[/green] {j}")


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
