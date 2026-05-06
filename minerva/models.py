from __future__ import annotations

from datetime import datetime

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator


OPTION_LETTERS = "ABCDE"


class CurriculumNode(BaseModel):
    key: str = Field(validation_alias=AliasChoices("key", "code"))
    label: str
    source_identifier: str | None = None
    children: list[CurriculumNode] = Field(default_factory=list)

    @property
    def code(self) -> str:
        """Compatibility alias for older CLI code and existing QuestionSet exports."""
        return self.key


class CurriculumVersionMetadata(BaseModel):
    label: str
    effective_from: str | None = None
    effective_to: str | None = None
    source_url: str | None = None
    source_file_name: str | None = None
    released_at: str | None = None


class CurriculumDocument(BaseModel):
    schema_version: str
    key: str
    title: str
    owner_name: str | None = None
    owner_key: str | None = None
    owner_type: str = "unknown"
    domain_name: str | None = None
    domain_key: str | None = None
    assessment_name: str | None = None
    assessment_key: str | None = None
    is_internal: bool = False
    version: CurriculumVersionMetadata
    root: CurriculumNode


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

    @field_validator("exam", mode="before")
    @classmethod
    def normalize_exam(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return {
            "primary": "primary_frca",
            "primary_frca": "primary_frca",
            "final": "final_frca",
            "final_frca": "final_frca",
        }.get(str(value), str(value))


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
