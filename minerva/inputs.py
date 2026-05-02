from __future__ import annotations

from pathlib import Path


def read_pdf_text(path: Path) -> str:
    """Extract text and tables from a PDF input file."""
    import pdfplumber

    from .embed import _clean_text, _extract_page

    parts = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            prose, tables = _extract_page(page)
            parts.append(_clean_text(prose))
            parts.extend(tables)
    return "\n\n".join(filter(None, parts))


def read_input_file(path: Path) -> str:
    """Read text from a PDF, Markdown, or plain text input file."""
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        return read_pdf_text(path)
    return path.read_text(encoding="utf-8")
