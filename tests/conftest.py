from datetime import datetime

import pytest

from minerva.models import CurriculumNode, Question, QuestionOption, QuestionSet


def make_options(correct_index: int = 0) -> list[QuestionOption]:
    labels = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"]
    return [
        QuestionOption(
            text=f"Option {label} text",
            is_correct=(i == correct_index),
            explanation=f"Explanation for option {label}",
        )
        for i, label in enumerate(labels)
    ]


@pytest.fixture
def sample_question():
    return Question(
        stem="A 45-year-old male presents for elective surgery.",
        lead="What is the most appropriate induction agent?",
        options=make_options(correct_index=2),
        explanation="Propofol is the standard induction agent for most elective procedures.",
    )


@pytest.fixture
def sample_question_set(sample_question):
    return QuestionSet(
        topic="Induction Agents",
        model="openai:gpt-4o",
        generated_at=datetime(2026, 4, 30, 12, 0, 0),
        questions=[sample_question],
    )


@pytest.fixture
def curriculum_tree():
    """Small tree for testing tree-walking functions."""
    return CurriculumNode(
        code="root",
        label="Root",
        children=[
            CurriculumNode(
                code="A1",
                label="Pharmacology",
                children=[
                    CurriculumNode(code="A1a", label="Opioids"),
                    CurriculumNode(code="A1b", label="NSAIDs"),
                ],
            ),
            CurriculumNode(
                code="B1",
                label="Physiology",
                children=[
                    CurriculumNode(code="B1a", label="Cardiac Output"),
                ],
            ),
        ],
    )
