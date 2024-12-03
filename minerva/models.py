from typing import List, Optional

from pydantic import BaseModel, Field

from .console import console


class Choice(BaseModel):
    id: int = Field(description="The id of the choice")
    text: str = Field(description="The text of the choice")


class Question(BaseModel):
    stem: str = Field(description="The stem of the single-best answer question, which sets the scene for the lead, but doesn not contain a question itself")
    lead: str = Field(description="The lead-in question of the single-best answer question")
    choices: List[Choice] = Field(description="A list of 5 possible choice answers for the single-best answer question")
    answer: int = Field(description="The id of the choice that is correct")
    explanation: str = Field(description="An explanation for the correct answer for the question")

    def show(self):
        console.rule(f"[bold red]Question")
        console.print(f"{self.stem}\n")
        console.print(f"[bold]{self.lead}\n")

        for choice in self.choices:
            console.print(f"\t> {choice.text}")

        console.print(f"\n[bold]Correct: [/bold]{[choice.text for choice in self.choices if self.answer == choice.id][0]}\n")
        console.print(self.explanation)


class Questions(BaseModel):
    qs: List[Question] = Field(description="A list of questions")


class Compentency(BaseModel):
    domain: Optional[str]
    subdomain: Optional[str]
    description: Optional[str]
