#! uv run
from __future__ import annotations

import asyncio
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
from rich.prompt import Prompt
from rich.table import Table

from minerva.agent import Deps, load_examples, make_agent
from minerva.console import console
from minerva.curriculum import EMBED_MODEL, flatten, l2_to_cosine, load, match_topic, node_path, search, search_table
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_node(exam: str | None, node_query: str | None) -> CurriculumNode | None:
    if not exam or not node_query:
        return None
    root = load(exam)  # type: ignore[arg-type]
    nodes = flatten(root)
    matches = search(nodes, node_query)
    if not matches:
        console.print(f"[yellow]No curriculum nodes matched '{node_query}'[/yellow]")
        return None
    if len(matches) == 1:
        return matches[0]
    # Interactive picker
    table = Table(show_header=True, header_style="bold")
    table.add_column("#", width=4)
    table.add_column("Code")
    table.add_column("Label")
    for i, n in enumerate(matches, 1):
        table.add_row(str(i), n.code, n.label)
    console.print(table)
    choice = Prompt.ask("Select node", choices=[str(i) for i in range(1, len(matches) + 1)])
    return matches[int(choice) - 1]


async def _generate(
    topic: str,
    count: int,
    model: str,
    exam: str | None,
    node: CurriculumNode | None,
    db: Path,
    embed_model: str,
    verbose: bool = False,
) -> QuestionSet:
    retriever = EmbedClient(db_path=db, embedding_model=embed_model)
    examples = load_examples()
    curriculum_path = node_path(load(exam), node.code) if (node and exam) else []  # type: ignore[arg-type]
    deps = Deps(retriever=retriever, curriculum_path=curriculum_path, examples=examples, verbose=verbose)

    prompt = (
        f"Write {count} dissimilar SBA question(s) on: {topic!r}.\n\n"
        "Each question should test application of knowledge, not simple recall — "
        "a candidate should need to reason from principles rather than just retrieve a fact. "
        "Use the retrieve tool to find relevant reference material before writing. "
        "Return the result as a QuestionSet."
    )

    ag = make_agent(model)
    result = await ag.run(prompt, deps=deps)
    qs = result.output
    qs.topic = topic
    qs.exam = exam
    qs.model = model
    if node:
        qs.curriculum_node_code = node.code
    return qs


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
            results = client._table.search(topic).limit(top).to_pandas()

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
    topic: Annotated[str, typer.Argument(help="Question topic")],
    count: Annotated[int, typer.Option("-c", "--count", help="Number of questions")] = 1,
    model: Annotated[str, typer.Option("-m", "--model", help="LLM model string (provider:name)")] = _DEFAULT_MODEL,
    exam: Annotated[Optional[Exam], typer.Option(help="Curriculum exam: 'primary' or 'final'")] = None,
    node: Annotated[Optional[str], typer.Option(help="Curriculum node code or search term")] = None,
    output: Annotated[Optional[Path], typer.Option("-o", "--output", help="Output directory for JSON + markdown")] = None,
    db: Annotated[Path, typer.Option(help="LanceDB path", envvar="LANCEDB_DIR")] = _DEFAULT_DB,
    embed_model: Annotated[str, typer.Option(help="Embedding model string")] = _DEFAULT_EMBED,
    verbose: Annotated[bool, typer.Option("-v", "--verbose", help="Show retrieval details")] = False,
) -> None:
    """Generate SBA questions on a topic."""
    curriculum_node = _resolve_node(exam, node)

    # Auto-match from topic if exam set but no explicit node given
    if exam and curriculum_node is None:
        with console.status("Matching curriculum node…"):
            matched = match_topic(topic, exam, db_path=db)  # type: ignore[arg-type]
        if matched:
            console.print(f"[dim]Matched curriculum node:[/dim] [cyan]{matched.code}[/cyan] {matched.label}")
            curriculum_node = matched
        else:
            console.print(f"[dim yellow]No confident curriculum match found for '{topic}'[/dim yellow]")

    if verbose:
        console.print(f"[dim]LLM model:       {model}[/dim]")
        console.print(f"[dim]Embedding model: {embed_model}[/dim]")

    with console.status(f"Generating {count} question(s) on '{topic}'…"):
        qs = asyncio.run(
            _generate(
                topic=topic,
                count=count,
                model=model,
                exam=exam,
                node=curriculum_node,
                db=db,
                embed_model=embed_model,
                verbose=verbose,
            )
        )

    for q in qs.questions:
        q.show()

    if output:
        j = save_json(qs, output)
        m = save_markdown(qs, output)
        console.print(f"\n[green]Saved:[/green] {j}\n[green]Saved:[/green] {m}")


@app.command()
def embed(
    path: Annotated[Path, typer.Argument(help="PDF file or directory to embed")],
    reset: Annotated[bool, typer.Option(help="Drop existing embeddings first")] = False,
    model: Annotated[str, typer.Option(help="Embedding model string")] = _DEFAULT_EMBED,
    db: Annotated[Path, typer.Option(help="LanceDB path", envvar="LANCEDB_DIR")] = _DEFAULT_DB,
) -> None:
    """Embed PDF documents into the vector store."""
    client = EmbedClient(db_path=db, embedding_model=model)

    if reset:
        client.reset()

    if path.is_dir():
        client.add_dir(path)
    elif path.is_file():
        client.add_pdf(path)
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
    node: Annotated[Optional[str], typer.Option(help="Curriculum node code or search term")] = None,
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
        curriculum_node = _resolve_node(exam, node)

        # Auto-match from topic if exam set but no explicit node given
        if exam and curriculum_node is None:
            with console.status("Matching curriculum node…"):
                matched = match_topic(topic, exam, db_path=db)  # type: ignore[arg-type]
            if matched:
                console.print(f"[dim]Matched curriculum node:[/dim] [cyan]{matched.code}[/cyan] {matched.label}")
                curriculum_node = matched
            else:
                console.print(f"[dim yellow]No confident curriculum match found for '{topic}'[/dim yellow]")

        save_dir = output or Path("./output")
        console.print(f"[dim]Questions will be saved to:[/dim] {save_dir}")

        if verbose:
            console.print(f"[dim]LLM model:       {model}[/dim]")
            console.print(f"[dim]Embedding model: {embed_model}[/dim]")

        with console.status(f"Generating {count} question(s) on '{topic}'…"):
            qs = asyncio.run(
                _generate(
                    topic=topic,
                    count=count,
                    model=model,
                    exam=exam,
                    node=curriculum_node,
                    db=db,
                    embed_model=embed_model,
                    verbose=verbose,
                )
            )
        saved = save_json(qs, save_dir)
        console.print(f"[green]Saved:[/green] {saved}")
    else:
        console.print("[red]Provide a JSON file or use --topic to generate questions.[/red]")
        raise typer.Exit(1)

    run_quiz(qs.questions)


if __name__ == "__main__":
    app()
