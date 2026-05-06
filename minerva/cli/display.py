from __future__ import annotations

from difflib import unified_diff

from minerva.console import console
from minerva.critique import apply_critique_result
from minerva.generation import GenerationPlanItem


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
