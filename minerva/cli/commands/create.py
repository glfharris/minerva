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
    plan_from_ranked_candidates,
    plan_from_subtree,
    resolve_topic_or_exit,
    run_async,
    save_outputs,
    show_critique,
    sum_usage,
    validate_count,
)
from minerva.console import console
from minerva.critique import critique_questions
from minerva.curriculum import _MATCH_THRESHOLD, _make_embedder, rematch_questions, search_table
from minerva.embed import EmbedClient
from minerva.generation import GenerationPlanItem, generate_questions, plan_node_codes
from minerva.paths import slugify
from minerva.render import show_question


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
    validate_count(count)
    curriculum_node, exam, topic = resolve_topic_or_exit(exam, node, topic, missing_msg="[red]Provide a topic or --node.[/red]")

    if verbose:
        console.print(f"[dim]LLM model:       {model}[/dim]")
        console.print(f"[dim]Embedding model: {embed_model}[/dim]")
        console.print(f"[dim]DB:              {db}[/dim]")

    if exam and not curriculum_node:
        with console.status("Loading embedding model…") as status:
            _make_embedder()
            status.update("Matching curriculum…")
            matches = search_table(topic, exam, db_path=db, n=10)
        candidates = [(score, cnode) for score, cnode in matches if score >= _MATCH_THRESHOLD]

        if not candidates:
            console.print(f"[yellow]No confident curriculum match for '{topic}' — generating without curriculum context.[/yellow]")
            generation_plan: list[GenerationPlanItem] = [GenerationPlanItem(node=None, count=count)]
        else:
            generation_plan = plan_from_ranked_candidates(candidates, count)

    elif curriculum_node and curriculum_node.children and count > 1 and not pin:
        generation_plan = plan_from_subtree(curriculum_node, topic, count)
    else:
        generation_plan = [GenerationPlanItem(node=curriculum_node, count=count)]

    with console.status("Loading embedding model…"):
        retriever = EmbedClient(db_path=db, embedding_model=embed_model)

    all_questions: list = []
    all_usages = []
    messages: list = []
    total_calls = len(generation_plan)
    prior_stems: list[str] = []

    for i, plan_item in enumerate(generation_plan):
        status_msg = (
            f"Generating question {i + 1}/{total_calls}…"
            if total_calls > 1
            else f"Generating {plan_item.count} question(s) on '{topic}'…"
        )
        with console.status(status_msg):
            qs_i, msgs_i, usage_i = run_async(
                generate_questions(
                    topic=topic,
                    count=plan_item.count,
                    model=model,
                    exam=exam,
                    node=plan_item.node,
                    retriever=retriever,
                    verbose=verbose,
                    prior_stems=prior_stems or None,
                )
            )
        if verbose and total_calls > 1:
            console.print(f"[dim]  Q{i + 1}: {format_usage(usage_i)}[/dim]")
        prior_stems.extend(q.stem for q in qs_i.questions)
        all_questions.extend(qs_i.questions)
        all_usages.append(usage_i)
        messages = msgs_i

    qs = qs_i
    qs.questions = all_questions
    if len(plan_node_codes(generation_plan)) != 1:
        qs.curriculum_node_code = None
    usage = sum_usage(*all_usages)

    if verbose:
        label = "Total" if total_calls > 1 else "Generate"
        console.print(f"[dim]{format_usage(usage, label=label)}[/dim]")

    with console.status("Matching curriculum nodes…"):
        rematch_questions(qs.questions, exam, db)

    if critique:
        with console.status("Critiquing questions…"):
            critique_result, critique_usage = run_async(critique_questions(qs, model))
        if verbose:
            console.print(f"[dim]{format_usage(critique_usage, label='Critique')}[/dim]")
        try:
            qs.questions = show_critique(critique_result, qs.questions, show_feedback=verbose, show_diff=verbose)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)
        with console.status("Matching revised curriculum nodes…"):
            rematch_questions(qs.questions, exam, db)

    for q in qs.questions:
        show_question(q, verbose=verbose)

    save_outputs(qs, output, markdown)

    if save_example:
        history_dir = Path("examples/histories")
        history_dir.mkdir(parents=True, exist_ok=True)
        dest = history_dir / f"{slugify(topic, fallback='example')}.json"
        dest.write_bytes(ModelMessagesTypeAdapter.dump_json(messages))
        console.print(f"[green]Saved example:[/green] {dest}")
