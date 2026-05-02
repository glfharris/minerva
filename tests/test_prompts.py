from minerva.prompts import build_generation_role


class TestBuildGenerationRole:
    def test_includes_primary_exam_context(self):
        prompt = build_generation_role("primary")

        assert "Primary FRCA" in prompt
        assert "basic sciences" in prompt

    def test_unknown_exam_uses_shared_base_only(self):
        prompt = build_generation_role("unknown")

        assert "Question structure" in prompt
        assert "Exam context" not in prompt
