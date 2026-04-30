import pytest
from pydantic import ValidationError

from minerva.models import Question, QuestionOption
from tests.conftest import make_options


class TestQuestionValidation:
    def test_valid_question_passes(self, sample_question):
        assert sample_question.lead == "What is the most appropriate induction agent?"

    def test_too_few_options_raises(self):
        with pytest.raises(ValidationError, match="5 options"):
            Question(
                stem="stem", lead="lead?",
                options=make_options()[:-1],
                explanation="exp",
            )

    def test_too_many_options_raises(self):
        extra = QuestionOption(letter="F", text="extra", is_correct=False, explanation="x")
        with pytest.raises(ValidationError, match="5 options"):
            Question(
                stem="stem", lead="lead?",
                options=make_options() + [extra],
                explanation="exp",
            )

    def test_wrong_letters_raises(self):
        options = [
            QuestionOption(letter=l, text=f"opt", is_correct=(l == "X"), explanation="x")
            for l in "ABCDX"
        ]
        with pytest.raises(ValidationError, match="in order"):
            Question(stem="stem", lead="lead?", options=options, explanation="exp")

    def test_out_of_order_letters_raises(self):
        options = [
            QuestionOption(letter=l, text="opt", is_correct=(l == "A"), explanation="x")
            for l in "ABECD"
        ]
        with pytest.raises(ValidationError, match="in order"):
            Question(stem="stem", lead="lead?", options=options, explanation="exp")

    def test_multiple_correct_raises(self):
        options = make_options("A")
        options[1] = QuestionOption(letter="B", text="opt", is_correct=True, explanation="x")
        with pytest.raises(ValidationError, match="1 correct"):
            Question(stem="stem", lead="lead?", options=options, explanation="exp")

    def test_no_correct_option_raises(self):
        options = [
            QuestionOption(letter=l, text="opt", is_correct=False, explanation="x")
            for l in "ABCDE"
        ]
        with pytest.raises(ValidationError, match="1 correct"):
            Question(stem="stem", lead="lead?", options=options, explanation="exp")


class TestCorrectOptionProperty:
    def test_returns_correct_option(self, sample_question):
        correct = sample_question.correct_option
        assert correct.letter == "C"
        assert correct.is_correct is True

    def test_correct_option_is_unique(self, sample_question):
        correct_options = [o for o in sample_question.options if o.is_correct]
        assert len(correct_options) == 1


class TestToMarkdown:
    def test_contains_stem(self, sample_question):
        assert sample_question.stem in sample_question.to_md()

    def test_contains_lead(self, sample_question):
        assert sample_question.lead in sample_question.to_md()

    def test_contains_all_option_texts(self, sample_question):
        md = sample_question.to_md()
        for opt in sample_question.options:
            assert opt.text in md

    def test_contains_overall_explanation(self, sample_question):
        assert sample_question.explanation in sample_question.to_md()

    def test_contains_correct_answer_marker(self, sample_question):
        assert "Correct:" in sample_question.to_md()
