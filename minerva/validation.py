from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from .curriculum import _ASSESSMENT_SEARCH_ORDER, _build_maps, load, normalize_assessment_key
from .models import QuestionSet


@dataclass(frozen=True)
class ValidationFinding:
    severity: str
    location: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    path: Path
    question_set: QuestionSet | None
    findings: list[ValidationFinding]

    @property
    def is_valid(self) -> bool:
        return not any(f.severity == "error" for f in self.findings)


def _known_curriculum_codes(exam: str | None) -> set[str]:
    normalized = normalize_assessment_key(exam)
    exams = (normalized,) if normalized else _ASSESSMENT_SEARCH_ORDER
    codes: set[str] = set()
    for ex in exams:
        node_map, _ = _build_maps(load(ex))
        codes.update(code for code in node_map if code != "root")
    return codes


def validate_questionset(qs: QuestionSet) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []

    if qs.exam is not None and normalize_assessment_key(qs.exam) is None:
        findings.append(ValidationFinding("error", "exam", "exam must be 'primary_frca', 'final_frca', or null"))

    if not qs.topic.strip():
        findings.append(ValidationFinding("error", "topic", "topic must not be empty"))
    if not qs.model.strip():
        findings.append(ValidationFinding("error", "model", "model must not be empty"))
    if not qs.questions:
        findings.append(ValidationFinding("error", "questions", "question set must contain at least one question"))
    if qs.curriculum_node_code and qs.curriculum_node_code not in _known_curriculum_codes(qs.exam):
        findings.append(
            ValidationFinding("error", "curriculum_node_code", f"unknown curriculum node code: {qs.curriculum_node_code}")
        )

    known_codes = _known_curriculum_codes(qs.exam)
    for idx, question in enumerate(qs.questions, start=1):
        qloc = f"questions[{idx}]"
        if not question.stem.strip():
            findings.append(ValidationFinding("error", f"{qloc}.stem", "stem must not be empty"))
        if not question.lead.strip():
            findings.append(ValidationFinding("error", f"{qloc}.lead", "lead must not be empty"))
        if not question.explanation.strip():
            findings.append(ValidationFinding("error", f"{qloc}.explanation", "explanation must not be empty"))
        if not question.title.strip():
            findings.append(ValidationFinding("warning", f"{qloc}.title", "title is empty"))

        if len(question.curriculum_node_codes) != len(question.curriculum_node_scores):
            findings.append(
                ValidationFinding(
                    "error",
                    f"{qloc}.curriculum_node_scores",
                    "curriculum node codes and scores must have the same length",
                )
            )
        for code in question.curriculum_node_codes:
            if code not in known_codes:
                findings.append(ValidationFinding("error", f"{qloc}.curriculum_node_codes", f"unknown node code: {code}"))

        for opt_idx, option in enumerate(question.options, start=1):
            oloc = f"{qloc}.options[{opt_idx}]"
            if not option.text.strip():
                findings.append(ValidationFinding("error", f"{oloc}.text", "option text must not be empty"))
            if not option.explanation.strip():
                findings.append(ValidationFinding("error", f"{oloc}.explanation", "option explanation must not be empty"))

    return findings


def validate_questionset_file(path: Path) -> ValidationResult:
    path = Path(path)
    try:
        qs = QuestionSet.model_validate_json(path.read_text())
    except (OSError, ValidationError, ValueError) as e:
        return ValidationResult(
            path=path,
            question_set=None,
            findings=[ValidationFinding("error", str(path), f"could not load QuestionSet: {e}")],
        )

    return ValidationResult(path=path, question_set=qs, findings=validate_questionset(qs))
