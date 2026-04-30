import pytest

from minerva.agent import _strip_tool_results, load_example_messages


class TestStripToolResults:
    def test_empty_list_returns_empty(self):
        assert _strip_tool_results([]) == []

    def test_non_model_request_passed_through_unchanged(self):
        sentinel = object()
        assert _strip_tool_results([sentinel])[0] is sentinel

    def test_tool_return_content_is_replaced(self):
        from pydantic_ai.messages import ModelRequest, ToolReturnPart

        part = ToolReturnPart(tool_name="retrieve", content="big chunk of text", tool_call_id="id1")
        msg = ModelRequest(parts=[part])
        result = _strip_tool_results([msg])
        assert result[0].parts[0].content == "[Retrieved reference material]"

    def test_non_tool_parts_unchanged(self):
        from pydantic_ai.messages import ModelRequest, UserPromptPart

        part = UserPromptPart(content="user message")
        msg = ModelRequest(parts=[part])
        result = _strip_tool_results([msg])
        assert result[0].parts[0].content == "user message"

    def test_mixed_parts_only_replaces_tool_returns(self):
        from pydantic_ai.messages import ModelRequest, ToolReturnPart, UserPromptPart

        user_part = UserPromptPart(content="question")
        tool_part = ToolReturnPart(tool_name="retrieve", content="chunk", tool_call_id="id2")
        msg = ModelRequest(parts=[user_part, tool_part])
        result = _strip_tool_results([msg])
        parts = result[0].parts
        assert parts[0].content == "question"
        assert parts[1].content == "[Retrieved reference material]"


class TestLoadExampleMessages:
    def test_nonexistent_directory_returns_empty(self, tmp_path):
        assert load_example_messages(tmp_path / "nonexistent") == []

    def test_empty_directory_returns_empty(self, tmp_path):
        assert load_example_messages(tmp_path) == []

    def test_malformed_json_skipped_silently(self, tmp_path):
        (tmp_path / "bad.json").write_text("not valid json")
        assert load_example_messages(tmp_path) == []
