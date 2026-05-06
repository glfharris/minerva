from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from pydantic_ai.usage import RunUsage

from .critique import critique_questions
from .conversion import convert_questions
from .curriculum import (
    AssessmentKey,
    ResolvedTopic,
    normalize_assessment_key,
    resolve_topic,
)
from .curriculum_match import (
    _MATCH_THRESHOLD,
    rematch_questions,
    search_table,
)
from .embed import RetrievedChunk, _make_embedder
from .embed import EmbedClient
from .generation import (
    GenerationPlanItem,
    generate_questions,
    plan_from_candidates,
    plan_node_codes,
    subtree_generation_plan,
)
from .models import CritiqueResult, Question, QuestionSet


class WorkflowInputError(ValueError):
    """Raised when a workflow cannot be started from the supplied inputs."""


ReviseQuestions = Callable[[CritiqueResult, list[Question]], list[Question]]
GenerationPlanReporter = Callable[[list[GenerationPlanItem], str], None]
NoConfidentMatchReporter = Callable[[str], None]


@dataclass(frozen=True)
class CreateQuestionSetRequest:
    topic: str | None
    count: int
    model: str
    exam: str | None
    node_code: str | None
    db_path: Path
    embedding_model: str
    verbose: bool = False
    critique: bool = False
    pin: bool = False


@dataclass(frozen=True)
class CreateQuestionSetResult:
    question_set: QuestionSet
    usage: RunUsage
    messages: list
    generation_plan: list[GenerationPlanItem]
    generation_usages: list[RunUsage] = field(default_factory=list)
    critique_usage: RunUsage | None = None
    retrieved_chunks: list[RetrievedChunk] = field(default_factory=list)


@dataclass(frozen=True)
class ConvertQuestionSetRequest:
    text: str
    topic: str
    model: str
    exam: str | None
    db_path: Path


@dataclass(frozen=True)
class ConvertQuestionSetResult:
    question_set: QuestionSet
    usage: RunUsage


def create_question_set(
    request: CreateQuestionSetRequest,
    *,
    revise_questions: ReviseQuestions | None = None,
    report_generation_plan: GenerationPlanReporter | None = None,
    report_no_confident_match: NoConfidentMatchReporter | None = None,
    run_async: Callable = asyncio.run,
) -> CreateQuestionSetResult:
    """Create a final QuestionSet from topic/node inputs.

    This is the application workflow behind the CLI command. Callers own
    presentation, output, and process exits.
    """
    if request.count < 1:
        raise WorkflowInputError("count must be at least 1")

    resolved = _resolve_create_topic(request.exam, request.node_code, request.topic)
    curriculum_node, exam, topic = resolved.node, resolved.exam, resolved.topic
    generation_plan = _create_generation_plan(
        topic=topic,
        count=request.count,
        exam=exam,
        curriculum_node=curriculum_node,
        db_path=request.db_path,
        pin=request.pin,
        report_generation_plan=report_generation_plan,
        report_no_confident_match=report_no_confident_match,
    )

    retriever = EmbedClient(db_path=request.db_path, embedding_model=request.embedding_model)

    all_questions: list[Question] = []
    all_usages: list[RunUsage] = []
    all_chunks: list[RetrievedChunk] = []
    messages: list = []
    prior_stems: list[str] = []

    for plan_item in generation_plan:
        qs_i, msgs_i, usage_i, chunks_i = run_async(
            generate_questions(
                topic=topic,
                count=plan_item.count,
                model=request.model,
                exam=exam,
                node=plan_item.node,
                retriever=retriever,
                verbose=request.verbose,
                prior_stems=prior_stems or None,
            )
        )
        prior_stems.extend(q.stem for q in qs_i.questions)
        all_questions.extend(qs_i.questions)
        all_usages.append(usage_i)
        all_chunks.extend(chunks_i)
        messages = msgs_i

    if not all_questions:
        raise WorkflowInputError("generation returned no questions")

    qs = qs_i
    qs.questions = all_questions
    if len(plan_node_codes(generation_plan)) != 1:
        qs.curriculum_node_code = None

    usage = sum(all_usages, RunUsage())
    rematch_questions(qs.questions, exam, request.db_path)

    critique_usage = None
    if request.critique:
        critique_result, critique_usage = run_async(critique_questions(qs, request.model))
        if revise_questions is None:
            raise WorkflowInputError("critique requires a revise_questions callback")
        qs.questions = revise_questions(critique_result, qs.questions)
        rematch_questions(qs.questions, exam, request.db_path)

    return CreateQuestionSetResult(
        question_set=qs,
        usage=usage,
        messages=messages,
        generation_plan=generation_plan,
        generation_usages=all_usages,
        critique_usage=critique_usage,
        retrieved_chunks=all_chunks,
    )


def convert_question_set(
    request: ConvertQuestionSetRequest,
    *,
    run_async: Callable = asyncio.run,
) -> ConvertQuestionSetResult:
    """Convert unstructured SBA text into a rematched QuestionSet."""
    normalized_exam = normalize_assessment_key(request.exam)
    if request.exam is not None and normalized_exam is None:
        raise WorkflowInputError(
            f"Unknown exam '{request.exam}'. Use primary_frca or final_frca."
        )

    qs, usage = run_async(convert_questions(request.text, request.topic, request.model))
    if normalized_exam:
        qs.exam = normalized_exam

    _make_embedder()
    rematch_questions(qs.questions, normalized_exam, request.db_path)

    return ConvertQuestionSetResult(question_set=qs, usage=usage)


def _resolve_create_topic(
    exam: str | None,
    node_code: str | None,
    topic: str | None,
) -> ResolvedTopic:
    resolved = resolve_topic(exam, node_code, topic)
    if resolved is None:
        if node_code:
            raise WorkflowInputError(f"No curriculum node found with code '{node_code}'")
        raise WorkflowInputError("Provide a topic or --node.")
    return resolved


def _create_generation_plan(
    *,
    topic: str,
    count: int,
    exam: AssessmentKey | None,
    curriculum_node,
    db_path: Path,
    pin: bool,
    report_generation_plan: GenerationPlanReporter | None,
    report_no_confident_match: NoConfidentMatchReporter | None,
) -> list[GenerationPlanItem]:
    if exam and not curriculum_node:
        _make_embedder()
        matches = search_table(topic, exam, db_path=db_path, n=10)
        candidates = [(score, cnode) for score, cnode in matches if score >= _MATCH_THRESHOLD]

        if not candidates:
            if report_no_confident_match:
                report_no_confident_match(topic)
            return [GenerationPlanItem(node=None, count=count)]

        plan = plan_from_candidates(candidates, count)
        if report_generation_plan:
            report_generation_plan(plan, "")
        return plan

    if curriculum_node and curriculum_node.children and count > 1 and not pin:
        plan = subtree_generation_plan(curriculum_node, topic, count, threshold=_MATCH_THRESHOLD)
        if report_generation_plan:
            report_generation_plan(plan, topic)
        return plan

    return [GenerationPlanItem(node=curriculum_node, count=count)]
