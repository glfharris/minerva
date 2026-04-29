from __future__ import annotations

from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from .console import console
from .models import Question


def run_quiz(questions: list[Question]) -> None:
    score = 0
    results: list[tuple[str, bool]] = []

    for i, question in enumerate(questions, start=1):
        console.print()
        console.rule(f"[bold]Question {i} of {len(questions)}")

        body = f"{question.stem}\n\n[bold]{question.lead}[/bold]\n\n"
        for opt in question.options:
            body += f"  [cyan]{opt.letter}.[/cyan] {opt.text}\n"

        console.print(Panel(body.rstrip(), expand=False))

        answer = Prompt.ask(
            "Your answer",
            choices=["A", "B", "C", "D", "E"],
            show_choices=True,
        ).upper()

        correct = question.correct_option
        correct_letter = correct.letter.upper()
        is_correct = answer == correct_letter
        score += int(is_correct)
        results.append((question.lead[:60], is_correct))

        if is_correct:
            console.print(f"[bold green]Correct![/bold green] {correct.letter}. {correct.text}")
        else:
            console.print(
                f"[bold red]Incorrect.[/bold red] "
                f"You chose {answer}. Correct answer: {correct_letter}. {correct.text}"
            )
        console.print(f"\n[dim]{question.explanation}[/dim]")

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
