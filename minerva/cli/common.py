from __future__ import annotations

import asyncio
from enum import StrEnum
import os
from pathlib import Path

import typer
from pydantic_ai.usage import RunUsage

from minerva.console import console
from minerva.curriculum import AssessmentKey, normalize_assessment_key, resolve_topic
from minerva.embed import EMBED_MODEL
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
