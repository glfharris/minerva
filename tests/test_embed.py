from minerva.embed import _chunk_text, _clean_text, _records_from_sections, _without_source_metadata
from minerva.inputs import _extract_epub_chapters, _table_to_markdown
from minerva.source_manifest import SourceMetadata

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


class TestRecordsFromSections:
    def test_records_include_source_metadata(self):
        metadata = SourceMetadata(
            source_id="peck_pharmacology",
            title="Pharmacology for Anaesthesia",
            source_type="book",
            author_or_publisher="Tom Peck",
            year="2021",
            url="https://example.com",
            doi="10.example/test",
            file_name="pharmacology.pdf",
        )

        records, table_count = _records_from_sections(
            [(0, "Some source text.", ["| Table |"])],
            "/docs/pharmacology.pdf",
            metadata,
        )

        assert table_count == 1
        assert len(records) == 2
        for record in records:
            assert record["source"] == "/docs/pharmacology.pdf"
            assert record["source_id"] == "peck_pharmacology"
            assert record["source_title"] == "Pharmacology for Anaesthesia"
            assert record["source_type"] == "book"
            assert record["source_author_or_publisher"] == "Tom Peck"
            assert record["source_year"] == "2021"
            assert record["source_url"] == "https://example.com"
            assert record["source_doi"] == "10.example/test"
            assert record["source_file_name"] == "pharmacology.pdf"

    def test_records_fall_back_to_file_metadata(self):
        records, _ = _records_from_sections(
            [(0, "Some source text.", [])],
            "/docs/Useful Book.pdf",
        )

        assert records[0]["source_id"] == "useful_book"
        assert records[0]["source_title"] == "Useful Book"
        assert records[0]["source_type"] == "pdf"

    def test_can_strip_source_metadata_for_legacy_tables(self):
        record = {
            "text": "Some source text.",
            "source": "/docs/source.pdf",
            "page": 0,
            "source_id": "source",
            "source_title": "Source",
            "source_type": "pdf",
        }

        stripped = _without_source_metadata(record)

        assert stripped == {
            "text": "Some source text.",
            "source": "/docs/source.pdf",
            "page": 0,
        }


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


def _make_test_epub(tmp_path, chapters):
    """Create a minimal EPUB from a list of (filename, html_body) tuples."""
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("test-id")
    book.set_title("Test Book")
    book.set_language("en")

    items = []
    for filename, html_body in chapters:
        item = epub.EpubHtml(title=filename, file_name=filename, lang="en")
        item.set_content(f"<html><body>{html_body}</body></html>".encode())
        book.add_item(item)
        items.append(item)

    book.spine = ["nav"] + items
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    path = tmp_path / "test.epub"
    epub.write_epub(str(path), book)
    return path


class TestExtractEpubChapters:
    def test_extracts_prose_from_chapters(self, tmp_path):
        path = _make_test_epub(tmp_path, [
            ("ch1.xhtml", "<p>Chapter one content.</p>"),
            ("ch2.xhtml", "<p>Chapter two content.</p>"),
        ])
        chapters = _extract_epub_chapters(path)
        # Should have at least 2 chapters with prose (nav may also appear)
        prose_texts = [prose for _, prose, _ in chapters if "Chapter" in prose]
        assert len(prose_texts) == 2
        assert "Chapter one content." in prose_texts[0]
        assert "Chapter two content." in prose_texts[1]

    def test_extracts_tables_as_markdown(self, tmp_path):
        html = (
            "<p>Some prose.</p>"
            "<table><tr><th>Drug</th><th>Dose</th></tr>"
            "<tr><td>Propofol</td><td>2 mg/kg</td></tr></table>"
        )
        path = _make_test_epub(tmp_path, [("ch1.xhtml", html)])
        chapters = _extract_epub_chapters(path)
        table_chapters = [(prose, tables) for _, prose, tables in chapters if tables]
        assert len(table_chapters) >= 1
        prose, tables = table_chapters[0]
        assert "| Drug | Dose |" in tables[0]
        assert "| Propofol | 2 mg/kg |" in tables[0]
        # Table text should not appear in prose (decomposed)
        assert "Propofol" not in prose

    def test_whitespace_only_chapter_is_skipped(self, tmp_path):
        path = _make_test_epub(tmp_path, [
            ("ch1.xhtml", "<p>  </p>"),
            ("ch2.xhtml", "<p>Has content.</p>"),
        ])
        chapters = _extract_epub_chapters(path)
        # No chapter should have whitespace-only prose (those are skipped)
        for _, prose, tables in chapters:
            assert prose.strip() or tables
        assert any("Has content." in prose for _, prose, _ in chapters)
