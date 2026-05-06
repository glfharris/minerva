from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated, Optional

import typer

from minerva.console import console
from minerva.curriculum import load_document
from minerva.output import load_questionset, save_website_export
from minerva.website_export import SourceMode, website_questionset_from_questionset


class SourceModeChoice(StrEnum):
    generated = "generated"
    converted = "converted"
    manual_json = "manual_json"
    external_bank = "external_bank"
    mixed = "mixed"
    unknown = "unknown"


def website_export(
    file: Annotated[Path, typer.Argument(help="QuestionSet JSON file to export")],
    source_mode: Annotated[SourceModeChoice, typer.Option(help="Origin type: generated, converted, manual_json, external_bank, mixed, unknown")] = SourceModeChoice.unknown,
    output: Annotated[Optional[Path], typer.Option("-o", "--output", help="Output path (file or directory)")] = None,
    exported_by: Annotated[Optional[str], typer.Option(help="Email or identifier of the exporter")] = None,
    curriculum_code: Annotated[Optional[str], typer.Option(help="Curriculum code override (e.g. rcoa_primary_frca)")] = None,
    curriculum_version: Annotated[Optional[str], typer.Option(help="Curriculum version label override")] = None,
    verbose: Annotated[bool, typer.Option("-v", "--verbose", help="Show extra detail")] = False,
) -> None:
    """Export a QuestionSet JSON file to the website import schema (WebsiteQuestionSetV1)."""
    try:
        qs = load_questionset(file)
    except Exception as e:
        console.print(f"[red]Could not load '{file}': {e}[/red]")
        raise typer.Exit(1)

    console.print(f"[dim]Loaded {len(qs.questions)} question(s) on '{qs.topic}'[/dim]")

    # Auto-derive curriculum metadata from exam when available
    if qs.exam and (curriculum_code is None or curriculum_version is None):
        try:
            doc = load_document(qs.exam)
            if doc:
                if curriculum_code is None:
                    curriculum_code = doc.key
                if curriculum_version is None:
                    curriculum_version = doc.version.label
        except ValueError:
            pass

    if verbose:
        console.print(f"[dim]Source mode:      {source_mode}[/dim]")
        if curriculum_code:
            console.print(f"[dim]Curriculum code:  {curriculum_code}[/dim]")
        if curriculum_version:
            console.print(f"[dim]Curriculum ver:   {curriculum_version}[/dim]")

    web_qs = website_questionset_from_questionset(
        qs,
        source_mode=source_mode,
        exported_by=exported_by,
        curriculum_code=curriculum_code,
        curriculum_version_label=curriculum_version,
    )

    # Resolve output path
    if output is None:
        out_path = file.with_stem(file.stem + "_website")
    elif not output.suffix:
        output.mkdir(parents=True, exist_ok=True)
        out_path = output / file.with_stem(file.stem + "_website").name
    else:
        out_path = output

    saved = save_website_export(web_qs, out_path)
    console.print(f"\n[green]Exported {len(web_qs.questions)} question(s):[/green] {saved}")
