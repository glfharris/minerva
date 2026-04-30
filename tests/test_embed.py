from minerva.embed import _chunk_text, _clean_text, _table_to_markdown

_CHUNK_SIZE = 300
_CHUNK_OVERLAP = 50


class TestCleanText:
    def test_fixes_hyphenated_line_breaks(self):
        assert _clean_text("anaes-\nthesia") == "anaesthesia"

    def test_collapses_multiple_spaces(self):
        assert _clean_text("hello   world") == "hello world"

    def test_collapses_newlines_to_space(self):
        assert _clean_text("hello\nworld") == "hello world"

    def test_strips_leading_and_trailing_whitespace(self):
        assert _clean_text("  hello  ") == "hello"

    def test_combined_hyphen_and_whitespace(self):
        assert _clean_text("  anaes-\nthesia   is   im-\nportant  ") == "anaesthesia is important"


class TestChunkText:
    def test_short_text_returned_as_single_chunk(self):
        text = " ".join(f"word{i}" for i in range(10))
        chunks = _chunk_text(text)
        assert chunks == [text]

    def test_empty_string_returns_empty_list(self):
        assert _chunk_text("") == []

    def test_long_text_splits_into_multiple_chunks(self):
        text = " ".join(f"w{i}" for i in range(700))
        assert len(_chunk_text(text)) >= 2

    def test_chunks_overlap_correctly(self):
        words = [f"w{i}" for i in range(400)]
        chunks = _chunk_text(" ".join(words))
        chunk0_words = chunks[0].split()
        chunk1_words = chunks[1].split()
        # Last OVERLAP words of chunk 0 should be first OVERLAP words of chunk 1
        assert chunk0_words[-_CHUNK_OVERLAP:] == chunk1_words[:_CHUNK_OVERLAP]

    def test_last_chunk_contains_final_word(self):
        words = [f"w{i}" for i in range(600)]
        chunks = _chunk_text(" ".join(words))
        assert chunks[-1].split()[-1] == "w599"

    def test_exactly_chunk_size_returns_single_chunk(self):
        text = " ".join(f"w{i}" for i in range(_CHUNK_SIZE))
        assert len(_chunk_text(text)) == 1


class TestTableToMarkdown:
    def test_basic_two_column_table(self):
        data = [["Drug", "Dose"], ["Propofol", "1–2 mg/kg"], ["Thiopental", "3–5 mg/kg"]]
        md = _table_to_markdown(data)
        assert "| Drug | Dose |" in md
        assert "| --- | --- |" in md
        assert "| Propofol | 1–2 mg/kg |" in md

    def test_none_cells_rendered_as_empty(self):
        data = [["H1", None], ["R1", "R2"]]
        md = _table_to_markdown(data)
        assert "|  |" in md

    def test_empty_rows_are_dropped(self):
        data = [["H1", "H2"], ["", ""], ["R1", "R2"]]
        md = _table_to_markdown(data)
        non_empty_lines = [l for l in md.splitlines() if l.strip()]
        assert len(non_empty_lines) == 3  # header + separator + one data row

    def test_all_empty_data_returns_empty_string(self):
        assert _table_to_markdown([["", ""], [None, None]]) == ""
