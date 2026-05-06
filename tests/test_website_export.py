from datetime import datetime

import pytest
from pydantic import ValidationError

from minerva.models import Question, QuestionOption
from minerva.website_export import (
    WebsiteQuestionOptionV1,
    WebsiteQuestionV1,
    content_fingerprints,
    website_questionset_from_questionset,
)


class TestWebsiteQuestionSetFromQuestionSet:
    def test_exports_schema_version_and_metadata(self, sample_question_set):
        exported_at = datetime(2026, 5, 1, 9, 30)

        web_export = website_questionset_from_questionset(
            sample_question_set,
            source_mode="generated",
            exported_at=exported_at,
            exported_by="editor@example.com",
            minerva_cli_version="0.2.0-test",
        )

        assert web_export.export_schema_version == "1"
        assert web_export.minerva_cli_version == "0.2.0-test"
        assert web_export.exported_at == exported_at
        assert web_export.exported_by == "editor@example.com"
        assert web_export.source_mode == "generated"
        assert len(web_export.questions) == 1

    def test_adds_stable_option_ids_and_correct_option_identity(self, sample_question_set):
        web_export = website_questionset_from_questionset(sample_question_set)
        question = web_export.questions[0]
        correct_options = [option for option in question.options if option.is_correct]

        assert len({option.option_id for option in question.options}) == 5
        assert all(option.option_id.startswith("opt_") for option in question.options)
        assert question.correct_option_id == correct_options[0].option_id

    def test_option_ids_are_deterministic(self, sample_question_set):
        first = website_questionset_from_questionset(sample_question_set)
        second = website_questionset_from_questionset(sample_question_set)

        first_ids = [option.option_id for option in first.questions[0].options]
        second_ids = [option.option_id for option in second.questions[0].options]

        assert first.questions[0].external_question_id == second.questions[0].external_question_id
        assert first_ids == second_ids

    def test_duplicate_questions_receive_unique_external_ids(self, sample_question_set):
        qs = sample_question_set.model_copy(
            update={"questions": [sample_question_set.questions[0], sample_question_set.questions[0]]}
        )

        web_export = website_questionset_from_questionset(qs)

        question_ids = [question.external_question_id for question in web_export.questions]
        assert question_ids[0].startswith("q_")
        assert question_ids[1] == f"{question_ids[0]}_2"

    def test_includes_generated_metadata_when_source_is_generated(self, sample_question_set):
        qs = sample_question_set.model_copy(update={"exam": "primary", "curriculum_node_code": "1_GA_P_6"})

        web_export = website_questionset_from_questionset(qs, source_mode="generated")
        generation = web_export.questions[0].generation_metadata

        assert generation is not None
        assert generation.method == "rag"
        assert generation.model == qs.model
        assert generation.topic == qs.topic
        assert generation.exam == "primary_frca"
        assert generation.curriculum_node_code == "1_GA_P_6"
        assert generation.generated_at == qs.generated_at

    def test_includes_conversion_metadata_when_source_is_converted(self, sample_question_set):
        web_export = website_questionset_from_questionset(sample_question_set, source_mode="converted")
        question = web_export.questions[0]

        assert question.generation_metadata is None
        assert question.conversion_metadata is not None
        assert question.conversion_metadata.conversion_model == sample_question_set.model
        assert question.conversion_metadata.converted_at == sample_question_set.generated_at

    def test_exports_curriculum_metadata(self, sample_question_set):
        question = sample_question_set.questions[0].model_copy(
            update={
                "curriculum_node_codes": ["1_GA_P_6"],
                "curriculum_node_scores": [0.91],
            }
        )
        qs = sample_question_set.model_copy(update={"exam": "primary", "questions": [question]})

        web_export = website_questionset_from_questionset(
            qs,
            curriculum_code="rcoa_primary_frca",
            curriculum_version_label="2.2",
        )

        curriculum = web_export.questions[0].curriculum
        assert curriculum.exam == "primary_frca"
        assert curriculum.curriculum_code == "rcoa_primary_frca"
        assert curriculum.curriculum_version_label == "2.2"
        assert curriculum.curriculum_node_codes == ["1_GA_P_6"]
        assert curriculum.curriculum_node_scores == [0.91]

    def test_json_round_trips_through_export_schema(self, sample_question_set):
        web_export = website_questionset_from_questionset(sample_question_set)

        loaded = web_export.__class__.model_validate_json(web_export.model_dump_json())

        assert loaded == web_export


class TestWebsiteQuestionValidation:
    def test_rejects_mismatched_correct_option_id(self):
        options = [
            WebsiteQuestionOptionV1(option_id="opt_a", text="A", is_correct=True, explanation="Correct"),
            WebsiteQuestionOptionV1(option_id="opt_b", text="B", is_correct=False, explanation="Wrong"),
            WebsiteQuestionOptionV1(option_id="opt_c", text="C", is_correct=False, explanation="Wrong"),
            WebsiteQuestionOptionV1(option_id="opt_d", text="D", is_correct=False, explanation="Wrong"),
            WebsiteQuestionOptionV1(option_id="opt_e", text="E", is_correct=False, explanation="Wrong"),
        ]

        with pytest.raises(ValidationError, match="correct_option_id"):
            WebsiteQuestionV1(
                external_question_id="q_1",
                title="Title",
                stem="Stem",
                lead="Lead?",
                options=options,
                correct_option_id="opt_b",
                explanation="Overall",
                fingerprints=content_fingerprints(
                    Question(stem="Stem", lead="Lead?", options=[
                        QuestionOption(text=o.text, is_correct=o.is_correct, explanation=o.explanation)
                        for o in options
                    ], explanation="Overall")
                ),
            )

    def test_rejects_duplicate_option_ids(self):
        options = [
            WebsiteQuestionOptionV1(option_id="opt_a", text="A", is_correct=True, explanation="Correct"),
            WebsiteQuestionOptionV1(option_id="opt_a", text="B", is_correct=False, explanation="Wrong"),
            WebsiteQuestionOptionV1(option_id="opt_c", text="C", is_correct=False, explanation="Wrong"),
            WebsiteQuestionOptionV1(option_id="opt_d", text="D", is_correct=False, explanation="Wrong"),
            WebsiteQuestionOptionV1(option_id="opt_e", text="E", is_correct=False, explanation="Wrong"),
        ]

        with pytest.raises(ValidationError, match="option IDs"):
            WebsiteQuestionV1(
                external_question_id="q_1",
                title="Title",
                stem="Stem",
                lead="Lead?",
                options=options,
                correct_option_id="opt_a",
                explanation="Overall",
                fingerprints=content_fingerprints(
                    Question(stem="Stem", lead="Lead?", options=[
                        QuestionOption(text=o.text, is_correct=o.is_correct, explanation=o.explanation)
                        for o in options
                    ], explanation="Overall")
                ),
            )
