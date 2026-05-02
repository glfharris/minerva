from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


OPTION_LETTERS = "ABCDE"


class CurriculumNode(BaseModel):
    code: str
    label: str
    children: list[CurriculumNode] = []


class QuestionOption(BaseModel):
    text: str = Field(description="Option text")
    is_correct: bool = Field(description="Whether this is the correct answer")
    explanation: str = Field(description="Why this option is correct (if is_correct) or why it is wrong (if a distractor)")


class Question(BaseModel):
    stem: str = Field(description="Scene-setting text that does not itself contain a question")
    lead: str = Field(description="The lead-in question")
    options: list[QuestionOption] = Field(description="Exactly 5 options, each with its own explanation")
    explanation: str = Field(description="Overall explanation providing educational context for the question — the key concept being tested and any important related points")
    title: str = Field(default="", description="A concise title (5–10 words) capturing the key concept tested, written as a topic label rather than a question, e.g. 'Rocuronium — mechanism of action at the NMJ' or 'One-lung ventilation — hypoxic pulmonary vasoconstriction'. Used for display and reference only.")
    curriculum_node_codes: list[str] = Field(default_factory=list)
    curriculum_node_scores: list[float] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_options(self) -> Question:
        if len(self.options) != 5:
            raise ValueError(f"Question must have exactly 5 options, got {len(self.options)}")
        correct = [o for o in self.options if o.is_correct]
        if len(correct) != 1:
            raise ValueError(f"Question must have exactly 1 correct option, got {len(correct)}")
        return self

    @property
    def correct_option(self) -> QuestionOption:
        for opt in self.options:
            if opt.is_correct:
                return opt
        raise ValueError(f"No correct option marked in question: {self.lead!r}")

    @property
    def correct_letter(self) -> str:
        for i, opt in enumerate(self.options):
            if opt.is_correct:
                return OPTION_LETTERS[i]
        raise ValueError(f"No correct option marked in question: {self.lead!r}")

    def with_sorted_options(self) -> Question:
        """Return a copy with options sorted by natsort."""
        from natsort import natsorted
        sorted_opts = natsorted(self.options, key=lambda o: o.text)
        return self.model_copy(update={"options": sorted_opts})

    def show(self, verbose: bool = False) -> None:
        from .console import console
        console.rule(f"[bold red]{self.title}[/bold red]" if self.title else "[bold red]Question[/bold red]")
        console.print(f"{self.stem}\n")
        console.print(f"[bold]{self.lead}\n")
        for i, opt in enumerate(self.options):
            letter = OPTION_LETTERS[i]
            console.print(f"\t[cyan]{letter}.[/cyan] {opt.text}")
        console.print(f"\n[bold]Correct:[/bold] {self.correct_letter}. {self.correct_option.text}\n")
        for i, opt in enumerate(self.options):
            letter = OPTION_LETTERS[i]
            prefix = "[green]✓[/green]" if opt.is_correct else "[red]✗[/red]"
            console.print(f"  {prefix} [bold]{letter}.[/bold] {opt.explanation}")
        console.print(f"\n{self.explanation}")
        if self.curriculum_node_codes:
            if verbose:
                from .curriculum import _build_maps, load
                node_map: dict[str, CurriculumNode] = {}
                for exam in ("primary", "final"):
                    nm, _ = _build_maps(load(exam))  # type: ignore[arg-type]
                    node_map.update(nm)
                scores = dict(zip(self.curriculum_node_codes, self.curriculum_node_scores))
                lines = []
                for c in self.curriculum_node_codes:
                    label = node_map[c].label if c in node_map else c
                    score = scores.get(c)
                    score_str = f" ({score:.2f})" if score is not None else ""
                    lines.append(f"  {c} — {label}{score_str}")
                console.print("\n[dim]Curriculum:\n" + "\n".join(lines) + "[/dim]")
            else:
                console.print(f"\n[dim]Curriculum: {', '.join(self.curriculum_node_codes)}[/dim]")

    def to_md(self) -> str:
        lines = ([f"## {self.title}", ""] if self.title else []) + [self.stem, "", f"**{self.lead}**", ""]
        for i, opt in enumerate(self.options):
            letter = OPTION_LETTERS[i]
            lines.append(f"**{letter}.** {opt.text}")
        lines += ["", f"**Correct:** {self.correct_letter}. {self.correct_option.text}", ""]
        for i, opt in enumerate(self.options):
            letter = OPTION_LETTERS[i]
            mark = "✓" if opt.is_correct else "✗"
            lines.append(f"**{mark} {letter}.** {opt.explanation}")
        lines += ["", self.explanation]
        return "\n".join(lines)


class QuestionSet(BaseModel):
    topic: str
    exam: str | None = None
    curriculum_node_code: str | None = None
    model: str
    generated_at: datetime = Field(default_factory=datetime.now)
    questions: list[Question]


class CritiquedQuestion(BaseModel):
    feedback: str = Field(
        description=(
            "Brief explanation of what was changed and why. "
            "Write 'No changes needed.' if the question was already satisfactory."
        )
    )
    question: Question = Field(description="The revised question, identical to input if no changes were needed")


class CritiqueResult(BaseModel):
    critiqued: list[CritiquedQuestion] = Field(
        description="One entry per question, in the same order as the input"
    )
