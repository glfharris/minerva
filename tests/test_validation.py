from minerva.models import QuestionSet
from minerva.validation import validate_questionset, validate_questionset_file


class TestValidateQuestionSet:
    def test_valid_questionset_has_no_findings(self, sample_question_set):
        question = sample_question_set.questions[0].model_copy(update={"title": "Induction agent choice"})
        qs = sample_question_set.model_copy(update={"questions": [question]})

        assert validate_questionset(qs) == []

    def test_missing_title_is_warning(self, sample_question_set):
        findings = validate_questionset(sample_question_set)

        assert any(f.location == "questions[1].title" and f.severity == "warning" for f in findings)

    def test_curriculum_codes_and_scores_must_match(self, sample_question_set):
        question = sample_question_set.questions[0].model_copy(
            update={
                "title": "Induction agent choice",
                "curriculum_node_codes": ["A1"],
                "curriculum_node_scores": [],
            }
        )
        qs = sample_question_set.model_copy(update={"questions": [question]})

        findings = validate_questionset(qs)

        assert any(f.location == "questions[1].curriculum_node_scores" for f in findings)

    def test_unknown_curriculum_code_is_error(self, sample_question_set):
        question = sample_question_set.questions[0].model_copy(
            update={
                "title": "Induction agent choice",
                "curriculum_node_codes": ["NO_SUCH_NODE"],
                "curriculum_node_scores": [0.9],
            }
        )
        qs = sample_question_set.model_copy(update={"exam": "primary", "questions": [question]})

        findings = validate_questionset(qs)

        assert any(f.location == "questions[1].curriculum_node_codes" and f.severity == "error" for f in findings)

    def test_empty_question_set_is_error(self, sample_question_set):
        qs = sample_question_set.model_copy(update={"questions": []})

        findings = validate_questionset(qs)

        assert any(f.location == "questions" and f.severity == "error" for f in findings)


class TestValidateQuestionSetFile:
    def test_invalid_json_returns_error_result(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not json")

        result = validate_questionset_file(path)

        assert not result.is_valid
        assert result.question_set is None
        assert result.findings[0].severity == "error"

    def test_valid_file_returns_question_set(self, tmp_path, sample_question_set):
        question = sample_question_set.questions[0].model_copy(update={"title": "Induction agent choice"})
        qs = sample_question_set.model_copy(update={"questions": [question]})
        path = tmp_path / "questions.json"
        path.write_text(qs.model_dump_json())

        result = validate_questionset_file(path)

        assert result.is_valid
        assert isinstance(result.question_set, QuestionSet)
