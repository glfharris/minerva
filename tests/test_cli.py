import pytest
from typer.testing import CliRunner

from minerva.cli.app import app
from minerva.generation import rank_subtree, subtree_generation_plan
from minerva.critique import apply_critique_result
from minerva.models import CritiqueResult, CurriculumNode

runner = CliRunner()


class TestCliApp:
    def test_help_lists_validate_command(self):
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "validate" in result.output

    def test_help_does_not_list_history_maintenance_script(self):
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "make-history" not in result.output

    def test_validate_accepts_valid_file_with_warnings(self, tmp_path, sample_question_set):
        path = tmp_path / "questions.json"
        path.write_text(sample_question_set.model_dump_json())

        result = runner.invoke(app, ["validate", str(path)])

        assert result.exit_code == 0
        assert "Valid with warnings" in result.output

    def test_validate_rejects_invalid_json(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not json")

        result = runner.invoke(app, ["validate", str(path)])

        assert result.exit_code == 1
        assert "Invalid" in result.output


class TestRankSubtree:
    def test_excludes_specified_parent_when_ranking_and_uses_breadcrumb_text(self, monkeypatch):
        parent = CurriculumNode(
            code="A1",
            label="Pharmacology",
            children=[
                CurriculumNode(code="A1a", label="Opioids"),
                CurriculumNode(code="A1b", label="NSAIDs"),
            ],
        )

        embedder = None

        class StubEmbedder:
            def __init__(self):
                self.texts = []

            def compute_source_embeddings(self, texts):
                self.texts = texts
                return [
                    [1.0, 0.0],  # topic
                    [0.8, 0.2],  # A1a
                    [0.1, 0.9],  # A1b
                ]

        embedder = StubEmbedder()
        monkeypatch.setattr("minerva.generation._make_embedder", lambda: embedder)

        ranked = rank_subtree(parent, "opioids")
        codes = [node.code for _, node in ranked]

        assert "A1" not in codes
        assert codes == ["A1a", "A1b"]
        assert embedder.texts == [
            "opioids",
            "Pharmacology. Opioids",
            "Pharmacology. NSAIDs",
        ]


class TestSubtreeGenerationPlan:
    def test_uses_ranked_descendants_when_threshold_met(self, monkeypatch):
        parent = CurriculumNode(
            code="A1",
            label="Pharmacology",
            children=[
                CurriculumNode(code="A1a", label="Opioids"),
                CurriculumNode(code="A1b", label="NSAIDs"),
            ],
        )

        monkeypatch.setattr(
            "minerva.generation.rank_subtree",
            lambda root, topic, n=10: [(0.9, root.children[0]), (0.6, root.children[1])],
        )

        plan = subtree_generation_plan(parent, "opioids", 3)

        codes = {item.node.code: item.count for item in plan if item.node is not None}
        assert sum(codes.values()) == 3
        assert set(codes) == {"A1a", "A1b"}
        assert "A1" not in codes

    def test_falls_back_to_parent_when_no_descendant_meets_threshold(self, monkeypatch):
        parent = CurriculumNode(
            code="A1",
            label="Pharmacology",
            children=[
                CurriculumNode(code="A1a", label="Opioids"),
                CurriculumNode(code="A1b", label="NSAIDs"),
            ],
        )

        monkeypatch.setattr(
            "minerva.generation.rank_subtree",
            lambda root, topic, n=10: [(0.2, root.children[0]), (0.1, root.children[1])],
        )

        plan = subtree_generation_plan(parent, "unrelated topic", 3)

        assert len(plan) == 1
        assert plan[0].node == parent
        assert plan[0].count == 3


class TestShowCritique:
    def test_raises_if_model_returns_wrong_number_of_questions(self, sample_question):
        critique_result = CritiqueResult(critiqued=[])

        with pytest.raises(ValueError, match="0 question\\(s\\) for 1 input"):
            apply_critique_result(critique_result, [sample_question])
