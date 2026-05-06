from __future__ import annotations

from pathlib import Path

import pytest
from pydantic_ai.usage import RunUsage

from minerva.curriculum import ResolvedTopic
from minerva.models import CritiqueResult, CritiquedQuestion, CurriculumNode
from minerva.workflows import (
    CreateQuestionSetRequest,
    ConvertQuestionSetRequest,
    WorkflowInputError,
    create_question_set,
    convert_question_set,
)


class TestCreateQuestionSetWorkflow:
    def test_matches_topic_to_curriculum_and_generates_questions(self, monkeypatch, sample_question_set):
        matched_node = CurriculumNode(code="1_GA_P_6", label="Pharmacology")
        calls = []
        rematches = []

        monkeypatch.setattr(
            "minerva.workflows.resolve_topic",
            lambda exam, node_code, topic: ResolvedTopic(node=None, exam="primary_frca", topic="Rocuronium"),
        )
        monkeypatch.setattr("minerva.workflows._make_embedder", lambda: None)
        monkeypatch.setattr(
            "minerva.workflows.search_table",
            lambda topic, exam, db_path, n: [(0.91, matched_node)],
        )

        class FakeEmbedClient:
            def __init__(self, db_path, embedding_model):
                self.db_path = db_path
                self.embedding_model = embedding_model

        async def fake_generate_questions(**kwargs):
            calls.append(kwargs)
            return sample_question_set.model_copy(deep=True), ["messages"], RunUsage()

        def fake_rematch_questions(questions, exam, db_path):
            rematches.append((questions, exam, db_path))

        monkeypatch.setattr("minerva.workflows.EmbedClient", FakeEmbedClient)
        monkeypatch.setattr("minerva.workflows.generate_questions", fake_generate_questions)
        monkeypatch.setattr("minerva.workflows.rematch_questions", fake_rematch_questions)

        result = create_question_set(
            CreateQuestionSetRequest(
                topic="Rocuronium",
                count=1,
                model="openai:test",
                exam="primary",
                node_code=None,
                db_path=Path("lancedb"),
                embedding_model="sentence-transformers:test",
            )
        )

        assert result.question_set.topic == sample_question_set.topic
        assert result.messages == ["messages"]
        assert result.generation_plan[0].node == matched_node
        assert calls[0]["topic"] == "Rocuronium"
        assert calls[0]["exam"] == "primary_frca"
        assert calls[0]["node"] == matched_node
        assert rematches == [(result.question_set.questions, "primary_frca", Path("lancedb"))]

    def test_runs_critique_and_rematches_revised_questions(self, monkeypatch, sample_question_set, sample_question):
        rematches = []

        monkeypatch.setattr(
            "minerva.workflows.resolve_topic",
            lambda exam, node_code, topic: ResolvedTopic(node=None, exam=None, topic="Converted topic"),
        )

        class FakeEmbedClient:
            def __init__(self, db_path, embedding_model):
                pass

        async def fake_generate_questions(**kwargs):
            return sample_question_set.model_copy(deep=True), [], RunUsage()

        async def fake_critique_questions(qs, model):
            return CritiqueResult(
                critiqued=[
                    CritiquedQuestion(
                        feedback="Revised",
                        question=sample_question.model_copy(update={"title": "Revised title"}),
                    )
                ]
            ), RunUsage()

        def fake_rematch_questions(questions, exam, db_path):
            rematches.append([q.title for q in questions])

        monkeypatch.setattr("minerva.workflows.EmbedClient", FakeEmbedClient)
        monkeypatch.setattr("minerva.workflows.generate_questions", fake_generate_questions)
        monkeypatch.setattr("minerva.workflows.critique_questions", fake_critique_questions)
        monkeypatch.setattr("minerva.workflows.rematch_questions", fake_rematch_questions)

        result = create_question_set(
            CreateQuestionSetRequest(
                topic="Converted topic",
                count=1,
                model="openai:test",
                exam=None,
                node_code=None,
                db_path=Path("lancedb"),
                embedding_model="sentence-transformers:test",
                critique=True,
            ),
            revise_questions=lambda critique_result, original: [
                critique_result.critiqued[0].question
            ],
        )

        assert result.question_set.questions[0].title == "Revised title"
        assert len(rematches) == 2
        assert rematches[-1] == ["Revised title"]

    def test_raises_workflow_input_error_for_missing_topic(self, monkeypatch):
        monkeypatch.setattr("minerva.workflows.resolve_topic", lambda exam, node_code, topic: None)

        with pytest.raises(WorkflowInputError, match="Provide a topic"):
            create_question_set(
                CreateQuestionSetRequest(
                    topic=None,
                    count=1,
                    model="openai:test",
                    exam=None,
                    node_code=None,
                    db_path=Path("lancedb"),
                    embedding_model="sentence-transformers:test",
                )
            )


class TestConvertQuestionSetWorkflow:
    def test_converts_and_rematches_questions(self, monkeypatch, sample_question_set):
        rematches = []

        async def fake_convert_questions(text, topic, model):
            assert text == "raw SBA text"
            assert topic == "Converted topic"
            assert model == "openai:test"
            return sample_question_set.model_copy(deep=True), RunUsage()

        def fake_rematch_questions(questions, exam, db_path):
            rematches.append((questions, exam, db_path))

        monkeypatch.setattr("minerva.workflows.convert_questions", fake_convert_questions)
        monkeypatch.setattr("minerva.workflows._make_embedder", lambda: None)
        monkeypatch.setattr("minerva.workflows.rematch_questions", fake_rematch_questions)

        result = convert_question_set(
            ConvertQuestionSetRequest(
                text="raw SBA text",
                topic="Converted topic",
                model="openai:test",
                exam="primary",
                db_path=Path("lancedb"),
            )
        )

        assert result.question_set.exam == "primary_frca"
        assert rematches == [(result.question_set.questions, "primary_frca", Path("lancedb"))]

    def test_rejects_unknown_exam_before_conversion(self, monkeypatch):
        converted = False

        async def fake_convert_questions(text, topic, model):
            nonlocal converted
            converted = True

        monkeypatch.setattr("minerva.workflows.convert_questions", fake_convert_questions)

        with pytest.raises(WorkflowInputError, match="Unknown exam"):
            convert_question_set(
                ConvertQuestionSetRequest(
                    text="raw",
                    topic="Topic",
                    model="openai:test",
                    exam="unknown",
                    db_path=Path("lancedb"),
                )
            )

        assert converted is False
