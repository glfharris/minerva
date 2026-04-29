from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .console import console


class CurriculumNode(BaseModel):
    code: str
    label: str
    children: list[CurriculumNode] = []


class QuestionOption(BaseModel):
    letter: str = Field(description="Option letter A–E")
    text: str = Field(description="Option text")
    is_correct: bool = Field(description="Whether this is the correct answer")
    explanation: str = Field(description="Why this option is correct (if is_correct) or why it is wrong (if a distractor)")


class Question(BaseModel):
    stem: str = Field(description="Scene-setting text that does not itself contain a question")
    lead: str = Field(description="The lead-in question")
    options: list[QuestionOption] = Field(description="Exactly 5 lettered options (A–E), each with its own explanation")
    explanation: str = Field(description="Overall explanation providing educational context for the question — the key concept being tested and any important related points")
    curriculum_node_code: str | None = None

    @property
    def correct_option(self) -> QuestionOption:
        for opt in self.options:
            if opt.is_correct:
                return opt
        raise ValueError(f"No correct option marked in question: {self.lead!r}")

    def show(self) -> None:
        console.rule("[bold red]Question")
        console.print(f"{self.stem}\n")
        console.print(f"[bold]{self.lead}\n")
        for opt in self.options:
            console.print(f"\t[cyan]{opt.letter}.[/cyan] {opt.text}")
        console.print(f"\n[bold]Correct:[/bold] {self.correct_option.letter}. {self.correct_option.text}\n")
        for opt in self.options:
            prefix = "[green]✓[/green]" if opt.is_correct else "[red]✗[/red]"
            console.print(f"  {prefix} [bold]{opt.letter}.[/bold] {opt.explanation}")
        console.print(f"\n{self.explanation}")

    def to_md(self) -> str:
        lines = [self.stem, "", f"**{self.lead}**", ""]
        for opt in self.options:
            lines.append(f"**{opt.letter}.** {opt.text}")
        lines += ["", f"**Correct:** {self.correct_option.letter}. {self.correct_option.text}", ""]
        for opt in self.options:
            mark = "✓" if opt.is_correct else "✗"
            lines.append(f"**{mark} {opt.letter}.** {opt.explanation}")
        lines += ["", self.explanation]
        return "\n".join(lines)


class QuestionSet(BaseModel):
    topic: str
    exam: str | None = None
    curriculum_node_code: str | None = None
    model: str
    generated_at: datetime = Field(default_factory=datetime.now)
    questions: list[Question]
