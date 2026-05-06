from datetime import datetime

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from minerva.cli.app import app
from minerva.embed import RetrievedChunk
from minerva.models import Question, QuestionOption
from minerva.website_export import (
    CONTENT_FINGERPRINT_HASH_ALGORITHM,
    WebsiteCurriculumMetadataV1,
    WebsiteQuestionOptionV1,
    WebsiteQuestionSetV1,
    WebsiteQuestionV1,
    citations_from_chunks,
    content_fingerprints,
    sources_from_chunks,
    website_questionset_from_questionset,
)

runner = CliRunner()


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


class TestContentFingerprints:
    def test_pins_documented_normalisation_and_hashes(self):
        question = Question(
            title="  Title  ",
            stem="  A   STEM\nWith   Spaces ",
            lead="What is the BEST answer?",
            options=[
                QuestionOption(text="Beta  option", is_correct=False, explanation="Wrong"),
                QuestionOption(text="alpha OPTION", is_correct=True, explanation="Correct"),
                QuestionOption(text="Gamma option", is_correct=False, explanation="Wrong"),
                QuestionOption(text="Delta option", is_correct=False, explanation="Wrong"),
                QuestionOption(text="Epsilon option", is_correct=False, explanation="Wrong"),
            ],
            explanation=" Overall   Explanation ",
        )

        fingerprints = content_fingerprints(question)

        assert fingerprints.hash_algorithm == CONTENT_FINGERPRINT_HASH_ALGORITHM
        assert fingerprints.hash_algorithm == "sha256-minerva-normalised-v1"
        assert fingerprints.content_hash == "a2956337ed4e5de0966f56049a3df9162dd2e9ce968724969bd2e8aa8274185e"
        assert fingerprints.stem_hash == "01a45f342f139f7a82bf76eb61c5ad3cd4b4e4739c145afd15da974fc4c50bbc"
        assert fingerprints.lead_hash == "625e136758c6b6454f6cac87db8427538d3716bce034238fa7c6f994f897698b"
        assert fingerprints.option_set_hash == "cb34b876472261133687ed72c7c28c417b9be60cd92a28da93c8b223e804238a"
        assert fingerprints.answer_hash == "cc53cce85e9e01469ac5463721941cd98d99c388337b453b2e80e3fd2815cea9"


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

    def test_rejects_mismatched_curriculum_scores_length(self):
        with pytest.raises(ValidationError, match="same length"):
            WebsiteCurriculumMetadataV1(
                curriculum_node_codes=["1_GA_P_6", "1_GA_P_7"],
                curriculum_node_scores=[0.9],
            )

    def test_rejects_wrong_option_count(self):
        options = [
            WebsiteQuestionOptionV1(option_id="opt_a", text="A", is_correct=True, explanation="Correct"),
            WebsiteQuestionOptionV1(option_id="opt_b", text="B", is_correct=False, explanation="Wrong"),
            WebsiteQuestionOptionV1(option_id="opt_c", text="C", is_correct=False, explanation="Wrong"),
        ]

        with pytest.raises(ValidationError, match="exactly 5 options"):
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
                    ] + [
                        QuestionOption(text="D", is_correct=False, explanation="Wrong"),
                        QuestionOption(text="E", is_correct=False, explanation="Wrong"),
                    ], explanation="Overall")
                ),
            )

    def test_rejects_zero_correct_options(self):
        options = [
            WebsiteQuestionOptionV1(option_id=f"opt_{c}", text=c, is_correct=False, explanation="Wrong")
            for c in "ABCDE"
        ]

        with pytest.raises(ValidationError, match="exactly 1 correct"):
            WebsiteQuestionV1(
                external_question_id="q_1",
                title="Title",
                stem="Stem",
                lead="Lead?",
                options=options,
                correct_option_id="opt_A",
                explanation="Overall",
                fingerprints=content_fingerprints(
                    Question(stem="Stem", lead="Lead?", options=[
                        QuestionOption(text=o.text, is_correct=o.is_correct, explanation=o.explanation)
                        for o in options
                    ], explanation="Overall")
                ),
            )

    def test_rejects_multiple_correct_options(self):
        options = [
            WebsiteQuestionOptionV1(option_id="opt_a", text="A", is_correct=True, explanation="Correct"),
            WebsiteQuestionOptionV1(option_id="opt_b", text="B", is_correct=True, explanation="Also correct"),
            WebsiteQuestionOptionV1(option_id="opt_c", text="C", is_correct=False, explanation="Wrong"),
            WebsiteQuestionOptionV1(option_id="opt_d", text="D", is_correct=False, explanation="Wrong"),
            WebsiteQuestionOptionV1(option_id="opt_e", text="E", is_correct=False, explanation="Wrong"),
        ]

        with pytest.raises(ValidationError, match="exactly 1 correct"):
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

    def test_rejects_empty_question_list(self):
        with pytest.raises(ValidationError, match="at least one question"):
            WebsiteQuestionSetV1(
                minerva_cli_version="0.1.0",
                questions=[],
            )

    def test_rejects_duplicate_external_question_ids(self, sample_question_set):
        web_export = website_questionset_from_questionset(sample_question_set)
        q = web_export.questions[0]

        with pytest.raises(ValidationError, match="unique"):
            WebsiteQuestionSetV1(
                minerva_cli_version="0.1.0",
                questions=[q, q],
            )


def _make_chunk(
    *,
    text: str = "Sample chunk text",
    source: str = "/docs/book.pdf",
    page: int = 0,
    similarity: float = 0.85,
    source_id: str | None = "src_abc",
    source_title: str | None = "A Textbook",
    source_type: str | None = "book",
    **kwargs,
) -> RetrievedChunk:
    return RetrievedChunk(
        text=text,
        source=source,
        page=page,
        similarity=similarity,
        source_id=source_id,
        source_title=source_title,
        source_type=source_type,
        **kwargs,
    )


class TestSourcesAndCitationsFromChunks:
    def test_sources_deduplicates_by_source_id(self):
        chunks = [
            _make_chunk(source_id="src_1", source_title="Book One", page=0),
            _make_chunk(source_id="src_1", source_title="Book One", page=5),
        ]

        sources = sources_from_chunks(chunks)

        assert len(sources) == 1
        assert sources[0].source_id == "src_1"
        assert sources[0].title == "Book One"

    def test_sources_skips_chunks_without_source_id(self):
        chunks = [
            _make_chunk(source_id=None),
            _make_chunk(source_id="src_1"),
        ]

        sources = sources_from_chunks(chunks)

        assert len(sources) == 1
        assert sources[0].source_id == "src_1"

    def test_sources_empty_for_all_legacy_chunks(self):
        chunks = [
            _make_chunk(source_id=None),
            _make_chunk(source_id=None),
        ]

        assert sources_from_chunks(chunks) == []

    def test_citations_one_per_chunk(self):
        chunks = [
            _make_chunk(source_id="src_1", page=0),
            _make_chunk(source_id="src_1", page=4),
            _make_chunk(source_id="src_2", page=9),
        ]

        citations = citations_from_chunks(chunks)

        assert len(citations) == 3
        assert all(c.citation_type == "retrieved" for c in citations)
        assert citations[0].page == "1"
        assert citations[1].page == "5"
        assert citations[2].page == "10"

    def test_citations_skips_without_source_id(self):
        chunks = [
            _make_chunk(source_id=None),
            _make_chunk(source_id="src_1", page=2),
        ]

        citations = citations_from_chunks(chunks)

        assert len(citations) == 1
        assert citations[0].source_id == "src_1"

    def test_citations_no_excerpt_by_default(self):
        chunks = [_make_chunk(text="Some detailed text here")]

        citations = citations_from_chunks(chunks)

        assert citations[0].concise_excerpt is None

    def test_citations_includes_excerpt_when_opted_in(self):
        chunks = [_make_chunk(text="Some detailed text here")]

        citations = citations_from_chunks(chunks, include_excerpt=True)

        assert citations[0].concise_excerpt == "Some detailed text here"

    def test_question_includes_sources_when_chunks_provided(self, sample_question_set):
        chunks = [
            _make_chunk(source_id="src_1", source_title="Pharmacology Text", page=3),
            _make_chunk(source_id="src_2", source_title="Physiology Text", page=7),
        ]

        web_export = website_questionset_from_questionset(
            sample_question_set,
            retrieved_chunks=chunks,
        )

        q = web_export.questions[0]
        assert len(q.sources) == 2
        assert q.sources[0].source_id == "src_1"
        assert q.sources[1].source_id == "src_2"
        assert len(q.citations) == 2
        assert q.citations[0].page == "4"
        assert q.citations[1].page == "8"

    def test_question_empty_sources_without_chunks(self, sample_question_set):
        web_export = website_questionset_from_questionset(sample_question_set)

        q = web_export.questions[0]
        assert q.sources == []
        assert q.citations == []


class TestWebsiteExportCommand:
    def test_exports_valid_website_json(self, tmp_path, sample_question_set):
        input_path = tmp_path / "questions.json"
        input_path.write_text(sample_question_set.model_dump_json())

        result = runner.invoke(app, ["website-export", str(input_path)])

        assert result.exit_code == 0, result.output
        out_path = tmp_path / "questions_website.json"
        assert out_path.exists()
        web_qs = WebsiteQuestionSetV1.model_validate_json(out_path.read_text())
        assert len(web_qs.questions) == 1
        assert "Exported 1 question" in result.output

    def test_respects_output_flag(self, tmp_path, sample_question_set):
        input_path = tmp_path / "questions.json"
        input_path.write_text(sample_question_set.model_dump_json())
        out_path = tmp_path / "custom_output.json"

        result = runner.invoke(app, ["website-export", str(input_path), "-o", str(out_path)])

        assert result.exit_code == 0, result.output
        assert out_path.exists()
        WebsiteQuestionSetV1.model_validate_json(out_path.read_text())

    def test_respects_source_mode(self, tmp_path, sample_question_set):
        input_path = tmp_path / "questions.json"
        input_path.write_text(sample_question_set.model_dump_json())

        result = runner.invoke(app, ["website-export", str(input_path), "--source-mode", "generated"])

        assert result.exit_code == 0, result.output
        out_path = tmp_path / "questions_website.json"
        web_qs = WebsiteQuestionSetV1.model_validate_json(out_path.read_text())
        assert web_qs.source_mode == "generated"

    def test_exits_with_error_on_invalid_file(self, tmp_path):
        bad_path = tmp_path / "missing.json"

        result = runner.invoke(app, ["website-export", str(bad_path)])

        assert result.exit_code == 1
        assert "Could not load" in result.output

    def test_output_directory_creates_file_inside(self, tmp_path, sample_question_set):
        input_path = tmp_path / "questions.json"
        input_path.write_text(sample_question_set.model_dump_json())
        out_dir = tmp_path / "exports"

        result = runner.invoke(app, ["website-export", str(input_path), "-o", str(out_dir)])

        assert result.exit_code == 0, result.output
        expected = out_dir / "questions_website.json"
        assert expected.exists()
