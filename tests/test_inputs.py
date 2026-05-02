from pathlib import Path

from minerva.inputs import read_input_file


class TestReadInputFile:
    def test_reads_markdown_as_text(self, tmp_path):
        path = tmp_path / "questions.md"
        path.write_text("# Questions\n\nA stem", encoding="utf-8")

        assert read_input_file(path) == "# Questions\n\nA stem"

    def test_reads_plain_text(self, tmp_path):
        path = tmp_path / "questions.txt"
        path.write_text("A plain text question", encoding="utf-8")

        assert read_input_file(path) == "A plain text question"

    def test_dispatches_pdf_to_pdf_reader(self, tmp_path, monkeypatch):
        path = tmp_path / "questions.pdf"
        path.write_bytes(b"%PDF")

        monkeypatch.setattr("minerva.inputs.read_pdf_text", lambda p: f"pdf:{Path(p).name}")

        assert read_input_file(path) == "pdf:questions.pdf"
