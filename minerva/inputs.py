from __future__ import annotations

from pathlib import Path

from .console import console


def _table_to_markdown(data: list[list]) -> str:
    """Convert pdfplumber table data (list of rows) to a markdown table string."""
    # Replace None cells with empty string
    rows = [[str(cell).strip() if cell is not None else "" for cell in row] for row in data]
    # Drop completely empty rows
    rows = [row for row in rows if any(cell for cell in row)]
    if not rows:
        return ""
    header = "| " + " | ".join(rows[0]) + " |"
    separator = "| " + " | ".join("---" for _ in rows[0]) + " |"
    body = "\n".join("| " + " | ".join(row) + " |" for row in rows[1:])
    return "\n".join(filter(None, [header, separator, body]))


def _extract_page(page) -> tuple[str, list[str]]:
    """Extract prose text and tables from a pdfplumber page.

    Returns (prose_text, list_of_markdown_table_strings).
    Tables are extracted from their bounding boxes; prose is extracted
    from the remaining area so table content is not double-counted.
    """
    tables = page.find_tables()
    table_texts = []

    for table in tables:
        data = table.extract()
        if data:
            md = _table_to_markdown(data)
            if md:
                table_texts.append(md)

    # Crop page to exclude table bounding boxes before extracting prose
    prose_page = page
    for table in tables:
        try:
            prose_page = prose_page.outside_bbox(table.bbox)
        except Exception as e:
            console.log(f"[dim]Warning: could not crop table region ({e}), prose may include table text[/dim]")

    prose = prose_page.extract_text() or ""
    return prose, table_texts


def _extract_epub_chapters(path: Path) -> list[tuple[int, str, list[str]]]:
    """Extract text and tables from EPUB chapters.

    Returns list of (chapter_index, prose_text, table_markdown_strings).
    """
    import ebooklib
    from bs4 import BeautifulSoup
    from ebooklib import epub

    book = epub.read_epub(str(path), options={"ignore_ncx": True})
    chapters: list[tuple[int, str, list[str]]] = []
    chapter_index = 0

    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "html.parser")

        # Extract tables and convert to markdown
        table_texts: list[str] = []
        for table_tag in soup.find_all("table"):
            rows: list[list[str]] = []
            for tr in table_tag.find_all("tr"):
                cells = tr.find_all(["td", "th"])
                rows.append([cell.get_text(strip=True) for cell in cells])
            md = _table_to_markdown(rows)
            if md:
                table_texts.append(md)
            table_tag.decompose()  # remove so prose doesn't double-count

        prose = soup.get_text(separator=" ", strip=True)
        if prose or table_texts:
            chapters.append((chapter_index, prose, table_texts))
        chapter_index += 1

    return chapters


def extract_sections(path: Path) -> list[tuple[int, str, list[str]]]:
    """Extract sections from a document file.

    Dispatches by file suffix (.pdf or .epub).
    Returns list of (section_index, prose_text, table_markdown_strings).
    """
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        import pdfplumber

        sections: list[tuple[int, str, list[str]]] = []
        with pdfplumber.open(str(path)) as pdf:
            for page_num, page in enumerate(pdf.pages):
                prose, tables = _extract_page(page)
                sections.append((page_num, prose, tables))
        return sections
    if suffix == ".epub":
        return _extract_epub_chapters(path)
    raise ValueError(f"Unsupported file format: {suffix!r} (expected .pdf or .epub)")


def read_document_text(path: Path) -> str:
    """Extract all text and tables from a PDF or EPUB file as a single string."""
    from .embed import _clean_text

    parts = []
    for _index, prose, tables in extract_sections(path):
        parts.append(_clean_text(prose))
        parts.extend(tables)
    return "\n\n".join(filter(None, parts))


def read_input_file(path: Path) -> str:
    """Read text from a PDF, Markdown, or plain text input file."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".epub":
        raise ValueError("EPUB files are not supported for conversion. Use the embed command instead.")
    if suffix == ".pdf":
        return read_document_text(path)
    return path.read_text(encoding="utf-8")
