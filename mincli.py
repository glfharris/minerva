#! uv run
from __future__ import annotations

import asyncio
from difflib import unified_diff
from enum import StrEnum
import logging
import os
from pathlib import Path
import re
import random
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

from minerva.agent import Deps, critique_questions, convert_questions, load_example_messages, make_agent
from pydantic_ai.usage import RunUsage
from minerva.console import console
from minerva.curriculum import _MATCH_THRESHOLD, _make_embedder, EMBED_MODEL, l2_to_cosine, load, match_question_nodes, node_path, search_table
from minerva.embed import EmbedClient
from minerva.models import CurriculumNode, QuestionSet
from minerva.output import load_questionset, save_json, save_markdown
from minerva.quiz import run_quiz

load_dotenv()

app = typer.Typer(no_args_is_help=True)


class Exam(StrEnum):
    primary = "primary"
    final = "final"


class Source(StrEnum):
    curriculum = "curriculum"
    docs = "docs"

_DEFAULT_MODEL = os.environ.get("MINERVA_MODEL", "openai:gpt-5.5")
_DEFAULT_EMBED = f"sentence-transformers:{EMBED_MODEL}"
_DEFAULT_DB = Path(os.environ.get("LANCEDB_DIR", "./lancedb"))


def _format_usage(usage: RunUsage, label: str = "Usage") -> str:
    req = usage.input_tokens or 0
    resp = usage.output_tokens or 0
    total = usage.total_tokens or (req + resp)
    return f"{label}: {req:,} in / {resp:,} out / {total:,} total tokens"


def _sum_usage(*usages: RunUsage) -> RunUsage:
    return sum(usages, RunUsage())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _save_outputs(qs: QuestionSet, output: Path, markdown: bool) -> None:
    j = save_json(qs, output)
    console.print(f"\n[green]Saved:[/green] {j}")
    if markdown:
        m = save_markdown(qs, output)
        console.print(f"[green]Saved:[/green] {m}")


def _show_critique(critique_result, original_questions: list, show_feedback: bool, show_diff: bool) -> list:
    """Display critique feedback and/or diff, then return the revised questions."""
    revised = []
    if show_feedback:
        console.rule("[bold]Critique feedback")

    for i, (cq, original) in enumerate(zip(critique_result.critiqued, original_questions), 1):
        revised.append(cq.question.with_sorted_options())

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


def _lookup_node(exam: Exam | None, code: str) -> tuple[CurriculumNode, Exam] | None:
    """Look up a curriculum node by exact code.

    If exam is None, searches both trees and derives the exam from whichever contains the node.
    """
    exams_to_search = [exam] if exam else [Exam.primary, Exam.final]
    for ex in exams_to_search:
        path = node_path(load(ex), code)  # type: ignore[arg-type]
        if path:
            return path[-1], ex
    console.print(f"[red]No curriculum node found with code '{code}'[/red]")
    return None


def _resolve_topic(
    exam: Exam | None,
    node: str | None,
    topic: str | None,
    missing_msg: str = "[red]Provide a topic or --node.[/red]",
) -> tuple[CurriculumNode | None, Exam | None, str]:
    """Resolve node code + topic into (curriculum_node, exam, topic).

    If *node* is given, looks it up and derives exam from it.
    If *topic* is not given, falls back to the node label.
    Raises typer.Exit(1) on any error.
    """
    curriculum_node: CurriculumNode | None = None
    if node:
        result = _lookup_node(exam, node)
        if result is None:
            raise typer.Exit(1)
        curriculum_node, exam = result
    if not topic:
        if curriculum_node:
            topic = curriculum_node.label
        else:
            console.print(missing_msg)
            raise typer.Exit(1)
    return curriculum_node, exam, topic


def _rematch_questions(questions: list, exam: str | None, db_path: Path) -> None:
    """Replace each question's curriculum node codes and scores with full-text semantic matches."""
    for q in questions:
        matches = match_question_nodes(q, exam, db_path=db_path)  # type: ignore[arg-type]
        q.curriculum_node_codes = [code for code, _ in matches]
        q.curriculum_node_scores = [score for _, score in matches]


async def _generate(
    topic: str,
    count: int,
    model: str,
    exam: str | None,
    node: CurriculumNode | None,
    retriever: EmbedClient,
    verbose: bool = False,
    prior_stems: list[str] | None = None,
) -> tuple[QuestionSet, list, RunUsage]:
    curriculum_path = node_path(load(exam), node.code) if (node and exam) else []  # type: ignore[arg-type]
    deps = Deps(
        retriever=retriever,
        curriculum_path=curriculum_path,
        exam=exam,
        verbose=verbose,
    )

    prior_clause = ""
    if prior_stems:
        stems_text = "\n\n".join(f"- {s}" for s in prior_stems)
        prior_clause = (
            "\n\nThe following stem(s) have already been written for this question set. "
            "Ensure your patient demographics and clinical presentation are clearly distinct from these:\n\n"
            f"{stems_text}"
        )
    prompt = (
        f"Write {count} dissimilar SBA question(s) on: {topic!r}.\n\n"
        "Each question should test application of knowledge, not simple recall — "
        "a candidate should need to reason from principles rather than just retrieve a fact. "
        "Use the retrieve tool to find relevant reference material before writing. "
        f"Return the result as a QuestionSet.{prior_clause}"
    )

    ag = make_agent(model)
    example_messages = load_example_messages(topic=topic, exam=exam)

    result = await ag.run(prompt, deps=deps, message_history=example_messages)
    qs = result.output
    qs.topic = topic
    qs.exam = exam
    qs.model = model
    if node:
        qs.curriculum_node_code = node.code
    qs.questions = [q.with_sorted_options() for q in qs.questions]
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
    verbose: Annotated[bool, typer.Option("-v", "--verbose", help="Show extra detail per result")] = False,
) -> None:
    """Search curriculum nodes or embedded documents for a topic."""
    if verbose:
        console.print(f"[dim]Embedding model: {_DEFAULT_EMBED}[/dim]")
        console.print(f"[dim]DB:              {db}[/dim]")

    if source == Source.curriculum:
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

        for score, node in matches:
            colour = "green" if score >= 0.4 else "yellow"
            row = [f"[{colour}]{score:.2f}[/{colour}]", node.code, node.label]
            if verbose:
                ancestors = node_path(root, node.code)[:-1]  # exclude the node itself
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
    verbose: Annotated[bool, typer.Option("-v", "--verbose", help="Show retrieval, curriculum, and token details")] = False,
    markdown: Annotated[bool, typer.Option(help="Also save a markdown file alongside the JSON")] = False,
    save_example: Annotated[bool, typer.Option(help="Save this run as a few-shot example")] = False,
    critique: Annotated[bool, typer.Option("--critique", help="Run a self-critique pass to improve questions")] = False,
) -> None:
    """Generate SBA questions on a topic."""
    curriculum_node, exam, topic = _resolve_topic(
        exam, node, topic,
        missing_msg="[red]Provide a topic or --node.[/red]",
    )

    if verbose:
        console.print(f"[dim]LLM model:       {model}[/dim]")
        console.print(f"[dim]Embedding model: {embed_model}[/dim]")
        console.print(f"[dim]DB:              {db}[/dim]")

    # --- Node selection ---
    if exam and not curriculum_node:
        with console.status("Loading embedding model…") as status:
            _make_embedder()
            status.update("Matching curriculum…")
            matches = search_table(topic, exam, db_path=db, n=10)
        candidates = [(score, cnode) for score, cnode in matches if score >= _MATCH_THRESHOLD]

        if not candidates:
            console.print(f"[yellow]No confident curriculum match for '{topic}' — generating without curriculum context.[/yellow]")
            generation_plan: list[tuple[CurriculumNode | None, int]] = [(None, count)]
        elif count == 1:
            score, selected = random.choice(candidates)
            console.print(f"Curriculum: [bold]{selected.code}[/bold] [dim](similarity {score:.2f})[/dim]")
            generation_plan = [(selected, 1)]
        else:
            selected_nodes = [candidates[i % len(candidates)][1] for i in range(count)]
            random.shuffle(selected_nodes)

            # Group by node so questions sharing a node are generated in one call
            node_counts: dict[str, int] = {}
            node_objects: dict[str, CurriculumNode] = {}
            for cnode in selected_nodes:
                node_counts[cnode.code] = node_counts.get(cnode.code, 0) + 1
                node_objects[cnode.code] = cnode

            console.print(f"Distributing {count} question(s) across {len(node_counts)} curriculum node(s):")
            for code, q_count in node_counts.items():
                cnode = node_objects[code]
                sc = next(s for s, cn in candidates if cn.code == code)
                qs_label = f"{q_count}q"
                console.print(f"  [bold]{cnode.code}[/bold] [dim](similarity {sc:.2f}, {qs_label})[/dim]")

            generation_plan = [(node_objects[code], q_count) for code, q_count in node_counts.items()]
    else:
        generation_plan = [(curriculum_node, count)]

    # --- Generate ---
    with console.status("Loading embedding model…"):
        retriever = EmbedClient(db_path=db, embedding_model=embed_model)

    all_questions: list = []
    all_usages: list[RunUsage] = []
    messages: list = []
    total_calls = len(generation_plan)
    prior_stems: list[str] = []

    for i, (gen_node, gen_count) in enumerate(generation_plan):
        status_msg = (
            f"Generating question {i + 1}/{total_calls}…"
            if total_calls > 1
            else f"Generating {gen_count} question(s) on '{topic}'…"
        )
        with console.status(status_msg):
            qs_i, msgs_i, usage_i = asyncio.run(
                _generate(
                    topic=topic,
                    count=gen_count,
                    model=model,
                    exam=exam,
                    node=gen_node,
                    retriever=retriever,
                    verbose=verbose,
                    prior_stems=prior_stems or None,
                )
            )
        if verbose and total_calls > 1:
            console.print(f"[dim]  Q{i + 1}: {_format_usage(usage_i)}[/dim]")
        prior_stems.extend(q.stem for q in qs_i.questions)
        all_questions.extend(qs_i.questions)
        all_usages.append(usage_i)
        messages = msgs_i

    qs = qs_i
    qs.questions = all_questions
    usage = _sum_usage(*all_usages)

    if verbose:
        label = "Total" if total_calls > 1 else "Generate"
        console.print(f"[dim]{_format_usage(usage, label=label)}[/dim]")

    with console.status("Matching curriculum nodes…"):
        _rematch_questions(qs.questions, exam, db)

    if critique:
        with console.status("Critiquing questions…"):
            critique_result, critique_usage = asyncio.run(critique_questions(qs, model))
        if verbose:
            console.print(f"[dim]{_format_usage(critique_usage, label='Critique')}[/dim]")
        qs.questions = _show_critique(critique_result, qs.questions, show_feedback=verbose, show_diff=verbose)

    for q in qs.questions:
        q.show(verbose=verbose)

    _save_outputs(qs, output, markdown)

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


@app.command()
def quiz(
    file: Annotated[Optional[Path], typer.Argument(help="JSON QuestionSet file to quiz from")] = None,
    topic: Annotated[Optional[str], typer.Option(help="Topic: generate questions then quiz")] = None,
    count: Annotated[int, typer.Option("-c", "--count", help="Number of questions to generate")] = 3,
    model: Annotated[str, typer.Option("-m", "--model", help="LLM model string (provider:name)")] = _DEFAULT_MODEL,
    exam: Annotated[Optional[Exam], typer.Option(help="Curriculum exam: 'primary' or 'final'")] = None,
    node: Annotated[Optional[str], typer.Option(help="Exact curriculum node code e.g. 1_GA_P_6")] = None,
    output: Annotated[Optional[Path], typer.Option("-o", "--output", help="Where to save generated JSON")] = None,
    db: Annotated[Path, typer.Option(help="LanceDB path", envvar="LANCEDB_DIR")] = _DEFAULT_DB,
    embed_model: Annotated[str, typer.Option(help="Embedding model string")] = _DEFAULT_EMBED,
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
        curriculum_node, exam, topic = _resolve_topic(exam, node, topic)

        save_dir = output or Path("./output")
        console.print(f"[dim]Questions will be saved to:[/dim] {save_dir}")

        if verbose:
            console.print(f"[dim]LLM model:       {model}[/dim]")
            console.print(f"[dim]Embedding model: {embed_model}[/dim]")
            console.print(f"[dim]DB:              {db}[/dim]")

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
            console.print(f"[dim]{_format_usage(usage, label='Generate')}[/dim]")

        with console.status("Matching curriculum nodes…"):
            _rematch_questions(qs.questions, exam, db)

        saved = save_json(qs, save_dir)
        console.print(f"[green]Saved:[/green] {saved}")
    else:
        console.print("[red]Provide a JSON file, --topic, or --node.[/red]")
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
    if verbose:
        console.print(f"[dim]LLM model:       {model}[/dim]")
    try:
        qs = load_questionset(file)
    except Exception as e:
        console.print(f"[red]Could not load '{file}': {e}[/red]")
        raise typer.Exit(1)

    console.print(f"[dim]Loaded {len(qs.questions)} question(s) on '{qs.topic}'[/dim]")

    with console.status("Critiquing questions…"):
        critique_result, critique_usage = asyncio.run(critique_questions(qs, model))

    if verbose:
        console.print(f"[dim]{_format_usage(critique_usage, label='Critique')}[/dim]")

    qs.questions = _show_critique(critique_result, qs.questions, show_feedback=True, show_diff=verbose)

    save_path = output or file.with_stem(file.stem + "_critiqued")
    j = save_json(qs, save_path)
    console.print(f"\n[green]Saved:[/green] {j}")


def _read_file(path: Path) -> str:
    """Read text from a .pdf, .md, or .txt file."""
    if path.suffix.lower() == ".pdf":
        import pdfplumber
        from minerva.embed import _extract_page, _clean_text
        parts = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                prose, tables = _extract_page(page)
                parts.append(_clean_text(prose))
                parts.extend(tables)
        return "\n\n".join(filter(None, parts))
    else:
        return path.read_text(encoding="utf-8")


@app.command()
def convert(
    input_file: Annotated[Optional[Path], typer.Argument(help="Text, Markdown, or PDF file containing SBA questions")] = None,
    text: Annotated[Optional[str], typer.Option("--text", help="Inline question text to convert")] = None,
    topic: Annotated[Optional[str], typer.Option("--topic", help="Topic label for the output QuestionSet")] = None,
    exam: Annotated[Optional[Exam], typer.Option(help="Exam type: 'primary' or 'final'")] = None,
    model: Annotated[str, typer.Option("-m", "--model", help="LLM model string (provider:name)")] = _DEFAULT_MODEL,
    output: Annotated[Path, typer.Option("-o", "--output")] = Path("./output"),
    db: Annotated[Path, typer.Option(help="LanceDB path", envvar="LANCEDB_DIR")] = _DEFAULT_DB,
    markdown: Annotated[bool, typer.Option(help="Also save a markdown file")] = False,
    verbose: Annotated[bool, typer.Option("-v", "--verbose", help="Show model and token details")] = False,
) -> None:
    """Convert unstructured SBA question text/PDF to structured QuestionSet JSON."""
    if input_file:
        if not input_file.exists():
            console.print(f"[red]File not found: {input_file}[/red]")
            raise typer.Exit(1)
        raw = _read_file(input_file)
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

    with console.status("Converting questions…"):
        qs, usage = asyncio.run(convert_questions(raw, derived_topic, model))

    if exam:
        qs.exam = exam
    with console.status("Loading embedding model…") as status:
        _make_embedder()
        status.update("Matching curriculum nodes…")
        _rematch_questions(qs.questions, exam, db)

    if verbose:
        console.print(f"[dim]{_format_usage(usage, label='Convert')}[/dim]")

    console.print(f"[green]Parsed {len(qs.questions)} question(s)[/green]")
    for q in qs.questions:
        q.show(verbose=verbose)

    _save_outputs(qs, output, markdown)




def _first_sentence(text: str) -> str:
    """Extract the first sentence from a block of text."""
    for sep in (". ", ".\n"):
        idx = text.find(sep)
        if idx != -1:
            return text[: idx + 1].strip()
    return text.strip()[:200]


@app.command("make-history")
def make_history(
    files: Annotated[list[Path], typer.Argument(help="QuestionSet JSON files to convert")],
    output: Annotated[Path, typer.Option("-o", "--output")] = Path("examples/histories"),
) -> None:
    """Convert QuestionSet JSON files into mock few-shot example histories."""
    import json as _json
    from datetime import datetime, timezone
    from pydantic_ai.messages import (
        ModelMessagesTypeAdapter,
        ModelRequest,
        ModelResponse,
        ToolCallPart,
        ToolReturnPart,
        UserPromptPart,
    )

    output.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)

    index_path = output / "index.json"
    index: dict[str, dict] = {}
    if index_path.exists():
        for entry in _json.loads(index_path.read_text()):
            index[entry["file"]] = entry

    for file in files:
        try:
            qs = load_questionset(file)
        except Exception as e:
            console.print(f"[red]Could not load '{file}': {e}[/red]")
            continue

        saved = 0
        for q in qs.questions:
            topic = q.title or _first_sentence(q.explanation)
            slug = re.sub(r"[^a-z0-9]+", "_", topic.lower()).strip("_")[:50]
            filename = f"{slug}.json"
            retrieve_id = f"mock_r_{slug[:12]}"
            final_id = f"mock_f_{slug[:12]}"

            single_qs = qs.model_copy(update={"questions": [q]})
            prompt = (
                f"Write 1 dissimilar SBA question(s) on: {topic!r}.\n\n"
                "Each question should test application of knowledge, not simple recall — "
                "a candidate should need to reason from principles rather than just retrieve a fact. "
                "Use the retrieve tool to find relevant reference material before writing. "
                "Return the result as a QuestionSet."
            )

            messages = [
                ModelRequest(parts=[UserPromptPart(content=prompt, timestamp=now)], timestamp=now),
                ModelResponse(parts=[ToolCallPart(tool_name="retrieve", args=f'{{"query": {topic!r}}}', tool_call_id=retrieve_id)], timestamp=now),
                ModelRequest(parts=[ToolReturnPart(tool_name="retrieve", content="[Retrieved reference material]", tool_call_id=retrieve_id, timestamp=now)], timestamp=now),
                ModelResponse(parts=[ToolCallPart(tool_name="final_result", args=single_qs.model_dump_json(), tool_call_id=final_id)], timestamp=now),
                ModelRequest(parts=[ToolReturnPart(tool_name="final_result", content="Final result processed.", tool_call_id=final_id, timestamp=now)], timestamp=now),
            ]

            (output / filename).write_bytes(ModelMessagesTypeAdapter.dump_json(messages))
            index[filename] = {"file": filename, "exam": qs.exam, "topic": topic}
            saved += 1

        console.print(f"[green]Saved {saved} example(s) from {file.name}[/green]")

    index_path.write_text(_json.dumps(list(index.values()), indent=2))
    console.print(f"[green]Index:[/green] {index_path} ({len(index)} entries)")


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
