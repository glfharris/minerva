from __future__ import annotations

from .models import OPTION_LETTERS, CurriculumNode, Question


def show_question(question: Question, verbose: bool = False) -> None:
    from .console import console

    console.rule(f"[bold red]{question.title}[/bold red]" if question.title else "[bold red]Question[/bold red]")
    console.print(f"{question.stem}\n")
    console.print(f"[bold]{question.lead}\n")
    for i, opt in enumerate(question.options):
        letter = OPTION_LETTERS[i]
        console.print(f"\t[cyan]{letter}.[/cyan] {opt.text}")
    console.print(f"\n[bold]Correct:[/bold] {question.correct_letter}. {question.correct_option.text}\n")
    for i, opt in enumerate(question.options):
        letter = OPTION_LETTERS[i]
        prefix = "[green]✓[/green]" if opt.is_correct else "[red]✗[/red]"
        console.print(f"  {prefix} [bold]{letter}.[/bold] {opt.explanation}")
    console.print(f"\n{question.explanation}")
    if question.curriculum_node_codes:
        if verbose:
            from .curriculum import _build_maps, load

            node_map: dict[str, CurriculumNode] = {}
            for exam in ("primary", "final"):
                nm, _ = _build_maps(load(exam))  # type: ignore[arg-type]
                node_map.update(nm)
            scores = dict(zip(question.curriculum_node_codes, question.curriculum_node_scores))
            lines = []
            for code in question.curriculum_node_codes:
                label = node_map[code].label if code in node_map else code
                score = scores.get(code)
                score_str = f" ({score:.2f})" if score is not None else ""
                lines.append(f"  {code} — {label}{score_str}")
            console.print("\n[dim]Curriculum:\n" + "\n".join(lines) + "[/dim]")
        else:
            console.print(f"\n[dim]Curriculum: {', '.join(question.curriculum_node_codes)}[/dim]")
