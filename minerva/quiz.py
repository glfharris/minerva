from __future__ import annotations

from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from .console import console
from .models import OPTION_LETTERS, Question


def run_quiz(questions: list[Question]) -> None:
    score = 0
    results: list[tuple[str, bool]] = []

    for i, question in enumerate(questions, start=1):
        console.print()
        console.rule(f"[bold]Question {i} of {len(questions)}")

        body = f"{question.stem}\n\n[bold]{question.lead}[/bold]\n\n"
        for j, opt in enumerate(question.options):
            body += f"  [cyan]{OPTION_LETTERS[j]}.[/cyan] {opt.text}\n"

        console.print(Panel(body.rstrip(), expand=False))

        answer = Prompt.ask(
            "Your answer",
            choices=["A", "B", "C", "D", "E"],
            show_choices=True,
        ).upper()

        correct_letter = question.correct_letter
        is_correct = answer == correct_letter
        score += int(is_correct)
        results.append((question.title or question.lead[:60], is_correct))

        # Re-display options with colour coding and per-option explanations
        lines = []
        for j, opt in enumerate(question.options):
            letter = OPTION_LETTERS[j]
            if letter == correct_letter:
                lines.append(f"  [bold green]{letter}.[/bold green] [green]{opt.text}[/green]")
                lines.append(f"    [dim]{opt.explanation}[/dim]")
            elif letter == answer:
                lines.append(f"  [bold red]{letter}.[/bold red] [red]{opt.text}[/red]")
                lines.append(f"    [dim]{opt.explanation}[/dim]")
            else:
                lines.append(f"  [dim]{letter}. {opt.text}[/dim]")
        reveal = "\n".join(lines)

        verdict = "[bold green]Correct![/bold green]" if is_correct else "[bold red]Incorrect.[/bold red]"
        console.print(Panel(
            f"{verdict}\n\n{reveal.rstrip()}\n\n[dim]{question.explanation}[/dim]",
            expand=False,
        ))

    # Summary table
    console.print()
    console.rule("[bold]Quiz Complete")
    table = Table(show_header=True, header_style="bold")
    table.add_column("#", width=4)
    table.add_column("Question", no_wrap=False)
    table.add_column("Result", width=10)

    for idx, (lead, correct) in enumerate(results, 1):
        mark = "[green]✓[/green]" if correct else "[red]✗[/red]"
        table.add_row(str(idx), lead, mark)

    console.print(table)
    console.print(f"\n[bold]Score: {score}/{len(questions)}[/bold]")
