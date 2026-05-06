from __future__ import annotations

import asyncio
from difflib import unified_diff
from enum import StrEnum
import os
from pathlib import Path

import typer
from pydantic_ai.usage import RunUsage

from minerva.console import console
from minerva.critique import apply_critique_result
from minerva.curriculum import AssessmentKey, _MATCH_THRESHOLD, EMBED_MODEL, normalize_assessment_key, resolve_topic
from minerva.generation import GenerationPlanItem, plan_from_candidates, subtree_generation_plan
from minerva.models import CurriculumNode, QuestionSet
from minerva.output import save_json, save_markdown


class Exam(StrEnum):
    primary = "primary"
    primary_frca = "primary_frca"
    final = "final"
    final_frca = "final_frca"


class Source(StrEnum):
    curriculum = "curriculum"
    docs = "docs"


DEFAULT_MODEL = os.environ.get("MINERVA_MODEL", "openai:gpt-5.5")
DEFAULT_EMBED = f"sentence-transformers:{EMBED_MODEL}"
DEFAULT_DB = Path(os.environ.get("LANCEDB_DIR", "./lancedb"))


def format_usage(usage: RunUsage, label: str = "Usage") -> str:
    req = usage.input_tokens or 0
    resp = usage.output_tokens or 0
    total = usage.total_tokens or (req + resp)
    return f"{label}: {req:,} in / {resp:,} out / {total:,} total tokens"


def sum_usage(*usages: RunUsage) -> RunUsage:
    return sum(usages, RunUsage())


def save_outputs(qs: QuestionSet, output: Path, markdown: bool) -> None:
    json_path = save_json(qs, output)
    console.print(f"\n[green]Saved:[/green] {json_path}")
    if markdown:
        md_path = save_markdown(qs, output)
        console.print(f"[green]Saved:[/green] {md_path}")


def show_generation_plan(plan: list[GenerationPlanItem], topic: str) -> None:
    if len(plan) == 1:
        item = plan[0]
        if item.node is None:
            return
        if item.score is None:
            console.print(
                f"[yellow]No confident descendant match for '{topic}' under {item.node.code} — "
                "generating on the specified node instead.[/yellow]"
            )
        else:
            console.print(f"Curriculum: [bold]{item.node.code}[/bold] [dim](similarity {item.score:.2f})[/dim]")
        return

    console.print(f"Distributing {sum(item.count for item in plan)} question(s) across {len(plan)} curriculum node(s):")
    for item in plan:
        if item.node is None:
            continue
        score = f"similarity {item.score:.2f}, " if item.score is not None else ""
        console.print(f"  [bold]{item.node.code}[/bold] [dim]({score}{item.count}q)[/dim]")


def plan_from_ranked_candidates(candidates: list[tuple[float, CurriculumNode]], count: int) -> list[GenerationPlanItem]:
    plan = plan_from_candidates(candidates, count)
    show_generation_plan(plan, "")
    return plan


def plan_from_subtree(root: CurriculumNode, topic: str, count: int) -> list[GenerationPlanItem]:
    plan = subtree_generation_plan(root, topic, count, threshold=_MATCH_THRESHOLD)
    show_generation_plan(plan, topic)
    return plan


def show_critique(critique_result, original_questions: list, show_feedback: bool, show_diff: bool) -> list:
    revised = apply_critique_result(critique_result, original_questions)

    if show_feedback:
        console.rule("[bold]Critique feedback")

    for i, (cq, original, revised_question) in enumerate(zip(critique_result.critiqued, original_questions, revised), 1):
        if show_feedback:
            console.print(f"[bold]Q{i}:[/bold] [dim]{cq.feedback}[/dim]")

        if show_diff:
            orig_lines = original.to_md().splitlines(keepends=True)
            new_lines = revised_question.to_md().splitlines(keepends=True)
            diff = list(unified_diff(orig_lines, new_lines, lineterm=""))
            if diff:
                for line in diff[2:]:
                    if line.startswith("+"):
                        console.print(f"[green]{line.rstrip()}[/green]", highlight=False)
                    elif line.startswith("-"):
                        console.print(f"[red]{line.rstrip()}[/red]", highlight=False)
                    elif line.startswith("@"):
                        console.print(f"[dim]{line.rstrip()}[/dim]", highlight=False)

    return revised


def resolve_topic_or_exit(
    exam: Exam | None,
    node: str | None,
    topic: str | None,
    missing_msg: str = "[red]Provide a topic or --node.[/red]",
) -> tuple[CurriculumNode | None, AssessmentKey | None, str]:
    resolved = resolve_topic(exam, node, topic)
    if resolved is None:
        if node:
            console.print(f"[red]No curriculum node found with code '{node}'[/red]")
        else:
            console.print(missing_msg)
        raise typer.Exit(1)
    return resolved.node, resolved.exam, resolved.topic


def normalize_exam_or_exit(exam: Exam | str | None) -> AssessmentKey | None:
    normalized = normalize_assessment_key(exam)
    if exam is not None and normalized is None:
        console.print(f"[red]Unknown exam '{exam}'. Use primary_frca or final_frca.[/red]")
        raise typer.Exit(1)
    return normalized


def validate_count(count: int) -> None:
    if count < 1:
        console.print("[red]--count must be at least 1.[/red]")
        raise typer.Exit(1)


def run_async(coro):
    return asyncio.run(coro)
