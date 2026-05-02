from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from minerva.console import console
from minerva.validation import validate_questionset_file


def validate(
    files: Annotated[list[Path], typer.Argument(help="QuestionSet JSON files to validate")],
) -> None:
    """Validate saved QuestionSet JSON files without calling an LLM."""
    has_errors = False

    for file in files:
        result = validate_questionset_file(file)
        if result.is_valid:
            question_count = len(result.question_set.questions) if result.question_set else 0
            label = "[yellow]Valid with warnings:[/yellow]" if result.findings else "[green]Valid:[/green]"
            console.print(f"{label} {file} [dim]({question_count} question(s))[/dim]")
            if result.findings:
                table = Table(show_header=True, header_style="bold")
                table.add_column("Severity", width=9)
                table.add_column("Location")
                table.add_column("Message")
                for finding in result.findings:
                    table.add_row("[yellow]warning[/yellow]", finding.location, finding.message)
                console.print(table)
            continue

        has_errors = True
        console.print(f"[red]Invalid:[/red] {file}")
        table = Table(show_header=True, header_style="bold")
        table.add_column("Severity", width=9)
        table.add_column("Location")
        table.add_column("Message")
        for finding in result.findings:
            colour = "red" if finding.severity == "error" else "yellow"
            table.add_row(f"[{colour}]{finding.severity}[/{colour}]", finding.location, finding.message)
        console.print(table)

    if has_errors:
        raise typer.Exit(1)
