from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field, model_validator

from .curriculum import normalize_assessment_key
from .models import Question, QuestionSet

if TYPE_CHECKING:
    from .embed import RetrievedChunk


EXPORT_SCHEMA_VERSION = "1"
CONTENT_FINGERPRINT_HASH_ALGORITHM = "sha256-minerva-normalised-v1"

SourceMode = Literal["generated", "converted", "manual_json", "external_bank", "mixed", "unknown"]
OriginType = SourceMode
OptionOrderingMode = Literal["fixed", "randomizable"]


def _normalise(value: str) -> str:
    return " ".join(value.casefold().split())


def _short_hash(*parts: str, length: int = 16) -> str:
    h = sha256()
    for part in parts:
        h.update(_normalise(part).encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()[:length]


def _unique_id(base: str, seen: set[str]) -> str:
    if base not in seen:
        seen.add(base)
        return base

    i = 2
    while f"{base}_{i}" in seen:
        i += 1
    value = f"{base}_{i}"
    seen.add(value)
    return value


def _content_parts(question: Question) -> list[str]:
    parts = [question.title, question.stem, question.lead, question.explanation]
    for option in question.options:
        parts.extend([option.text, option.explanation, str(option.is_correct)])
    return parts


def _option_id(question_id: str, option_text: str, seen: set[str]) -> str:
    return _unique_id(f"opt_{_short_hash(question_id, option_text, length=12)}", seen)


def _question_id(question: Question, seen: set[str]) -> str:
    return _unique_id(f"q_{_short_hash(*_content_parts(question))}", seen)


def _minerva_cli_version() -> str:
    try:
        return version("minerva")
    except PackageNotFoundError:
        return "unknown"


class WebsiteSourceV1(BaseModel):
    source_id: str
    title: str
    source_type: Literal["book", "article", "web_page", "manual", "curriculum", "pdf", "unknown"] = "unknown"
    author_or_publisher: str | None = None
    year: str | None = None
    url: str | None = None
    doi: str | None = None
    file_name: str | None = None


class WebsiteCitationV1(BaseModel):
    source_id: str
    page: str | None = None
    section: str | None = None
    url_anchor: str | None = None
    citation_type: Literal["retrieved", "manual", "imported"] = "imported"
    support_note: str | None = None
    concise_excerpt: str | None = None


class WebsiteGenerationMetadataV1(BaseModel):
    method: str = "rag"
    model: str
    prompt_version: str | None = None
    topic: str
    exam: str | None = None
    curriculum_node_code: str | None = None
    generated_at: datetime | None = None
    token_usage: dict[str, int] | None = None
    estimated_cost: str | None = None
    retrieval_summary: str | None = None


class WebsiteConversionMetadataV1(BaseModel):
    converter: str = "minerva"
    conversion_model: str | None = None
    converted_at: datetime | None = None
    input_type: Literal["pdf", "markdown", "text", "json", "unknown"] = "unknown"
    source_title: str | None = None
    source_url: str | None = None
    source_file_name: str | None = None
    source_page: str | None = None
    section: str | None = None
    anchor: str | None = None


class WebsiteCurriculumMetadataV1(BaseModel):
    exam: str | None = None
    curriculum_code: str | None = None
    curriculum_version_label: str | None = None
    curriculum_node_codes: list[str] = Field(default_factory=list)
    curriculum_node_scores: list[float] = Field(default_factory=list)
    curriculum_path: str | None = None

    @model_validator(mode="after")
    def validate_scores(self) -> WebsiteCurriculumMetadataV1:
        if len(self.curriculum_node_codes) != len(self.curriculum_node_scores):
            raise ValueError("curriculum node codes and scores must have the same length")
        return self


class WebsiteContentFingerprintsV1(BaseModel):
    hash_algorithm: str = CONTENT_FINGERPRINT_HASH_ALGORITHM
    content_hash: str
    stem_hash: str
    lead_hash: str
    option_set_hash: str
    answer_hash: str


class WebsiteQuestionOptionV1(BaseModel):
    option_id: str
    text: str
    is_correct: bool
    explanation: str


class WebsiteQuestionV1(BaseModel):
    external_question_id: str
    source_question_id: str | None = None
    title: str
    stem: str
    lead: str
    options: list[WebsiteQuestionOptionV1]
    correct_option_id: str
    explanation: str
    option_ordering_mode: OptionOrderingMode = "fixed"
    curriculum: WebsiteCurriculumMetadataV1 = Field(default_factory=WebsiteCurriculumMetadataV1)
    origin_type: OriginType | None = None
    created_at: datetime | None = None
    generated_by: str | None = None
    converted_by: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    generation_metadata: WebsiteGenerationMetadataV1 | None = None
    conversion_metadata: WebsiteConversionMetadataV1 | None = None
    sources: list[WebsiteSourceV1] = Field(default_factory=list)
    citations: list[WebsiteCitationV1] = Field(default_factory=list)
    fingerprints: WebsiteContentFingerprintsV1

    @model_validator(mode="after")
    def validate_options(self) -> WebsiteQuestionV1:
        if len(self.options) != 5:
            raise ValueError(f"question must have exactly 5 options, got {len(self.options)}")

        option_ids = [option.option_id for option in self.options]
        if len(set(option_ids)) != len(option_ids):
            raise ValueError("option IDs must be unique within a question")

        correct_options = [option for option in self.options if option.is_correct]
        if len(correct_options) != 1:
            raise ValueError(f"question must have exactly 1 correct option, got {len(correct_options)}")
        if correct_options[0].option_id != self.correct_option_id:
            raise ValueError("correct_option_id must match the correct option")

        return self


class WebsiteQuestionSetV1(BaseModel):
    export_schema_version: Literal["1"] = EXPORT_SCHEMA_VERSION
    minerva_cli_version: str
    exported_at: datetime = Field(default_factory=datetime.now)
    exported_by: str | None = None
    source_mode: SourceMode = "unknown"
    questions: list[WebsiteQuestionV1]

    @model_validator(mode="after")
    def validate_questions(self) -> WebsiteQuestionSetV1:
        if not self.questions:
            raise ValueError("question set must contain at least one question")
        question_ids = [question.external_question_id for question in self.questions]
        if len(set(question_ids)) != len(question_ids):
            raise ValueError("external question IDs must be unique within an export")
        return self


def content_fingerprints(question: Question) -> WebsiteContentFingerprintsV1:
    option_parts = [option.text for option in question.options]
    answer = question.correct_option.text
    return WebsiteContentFingerprintsV1(
        content_hash=_short_hash(*_content_parts(question), length=64),
        stem_hash=_short_hash(question.stem, length=64),
        lead_hash=_short_hash(question.lead, length=64),
        option_set_hash=_short_hash(*sorted(option_parts, key=_normalise), length=64),
        answer_hash=_short_hash(answer, length=64),
    )


_VALID_SOURCE_TYPES = {"book", "article", "web_page", "manual", "curriculum", "pdf", "unknown"}


def sources_from_chunks(chunks: list[RetrievedChunk]) -> list[WebsiteSourceV1]:
    """Deduplicated WebsiteSourceV1 list from retrieved chunks.

    Chunks without source_id are skipped. First occurrence wins.
    """
    seen: dict[str, WebsiteSourceV1] = {}
    for chunk in chunks:
        if not chunk.source_id or chunk.source_id in seen:
            continue
        source_type = chunk.source_type if chunk.source_type in _VALID_SOURCE_TYPES else "unknown"
        seen[chunk.source_id] = WebsiteSourceV1(
            source_id=chunk.source_id,
            title=chunk.source_title or Path(chunk.source).name,
            source_type=source_type,
            author_or_publisher=chunk.author_or_publisher,
            year=chunk.year,
            url=chunk.url,
            doi=chunk.doi,
            file_name=chunk.file_name,
        )
    return list(seen.values())


def citations_from_chunks(
    chunks: list[RetrievedChunk],
    *,
    include_excerpt: bool = False,
    max_excerpt_len: int = 200,
) -> list[WebsiteCitationV1]:
    """One citation per chunk. Chunks without source_id are skipped."""
    citations = []
    for chunk in chunks:
        if not chunk.source_id:
            continue
        citations.append(WebsiteCitationV1(
            source_id=chunk.source_id,
            page=str(chunk.page + 1),
            citation_type="retrieved",
            concise_excerpt=chunk.text[:max_excerpt_len] if include_excerpt else None,
        ))
    return citations


def website_question_from_question(
    question: Question,
    question_set: QuestionSet,
    *,
    external_question_id: str,
    source_mode: SourceMode,
    option_ordering_mode: OptionOrderingMode = "fixed",
    curriculum_code: str | None = None,
    curriculum_version_label: str | None = None,
    retrieved_chunks: list[RetrievedChunk] | None = None,
) -> WebsiteQuestionV1:
    exam = normalize_assessment_key(question_set.exam)
    option_ids: set[str] = set()
    options = [
        WebsiteQuestionOptionV1(
            option_id=_option_id(external_question_id, option.text, option_ids),
            text=option.text,
            is_correct=option.is_correct,
            explanation=option.explanation,
        )
        for option in question.options
    ]
    correct_option_id = next(option.option_id for option in options if option.is_correct)

    generation_metadata = None
    conversion_metadata = None
    if source_mode == "generated":
        generation_metadata = WebsiteGenerationMetadataV1(
            model=question_set.model,
            topic=question_set.topic,
            exam=exam,
            curriculum_node_code=question_set.curriculum_node_code,
            generated_at=question_set.generated_at,
        )
    elif source_mode == "converted":
        conversion_metadata = WebsiteConversionMetadataV1(
            conversion_model=question_set.model,
            converted_at=question_set.generated_at,
        )

    sources = sources_from_chunks(retrieved_chunks) if retrieved_chunks else []
    citations = citations_from_chunks(retrieved_chunks) if retrieved_chunks else []

    return WebsiteQuestionV1(
        external_question_id=external_question_id,
        title=question.title,
        stem=question.stem,
        lead=question.lead,
        options=options,
        correct_option_id=correct_option_id,
        explanation=question.explanation,
        option_ordering_mode=option_ordering_mode,
        curriculum=WebsiteCurriculumMetadataV1(
            exam=exam,
            curriculum_code=curriculum_code,
            curriculum_version_label=curriculum_version_label,
            curriculum_node_codes=question.curriculum_node_codes,
            curriculum_node_scores=question.curriculum_node_scores,
        ),
        origin_type=source_mode,
        created_at=question_set.generated_at,
        generated_by="minerva" if source_mode == "generated" else None,
        converted_by="minerva" if source_mode == "converted" else None,
        generation_metadata=generation_metadata,
        conversion_metadata=conversion_metadata,
        sources=sources,
        citations=citations,
        fingerprints=content_fingerprints(question),
    )


def website_questionset_from_questionset(
    question_set: QuestionSet,
    *,
    source_mode: SourceMode = "unknown",
    exported_at: datetime | None = None,
    exported_by: str | None = None,
    minerva_cli_version: str | None = None,
    option_ordering_mode: OptionOrderingMode = "fixed",
    curriculum_code: str | None = None,
    curriculum_version_label: str | None = None,
    retrieved_chunks: list[RetrievedChunk] | None = None,
) -> WebsiteQuestionSetV1:
    question_ids: set[str] = set()
    questions = [
        website_question_from_question(
            question,
            question_set,
            external_question_id=_question_id(question, question_ids),
            source_mode=source_mode,
            option_ordering_mode=option_ordering_mode,
            curriculum_code=curriculum_code,
            curriculum_version_label=curriculum_version_label,
            retrieved_chunks=retrieved_chunks,
        )
        for question in question_set.questions
    ]

    return WebsiteQuestionSetV1(
        minerva_cli_version=minerva_cli_version or _minerva_cli_version(),
        exported_at=exported_at or datetime.now(),
        exported_by=exported_by,
        source_mode=source_mode,
        questions=questions,
    )
