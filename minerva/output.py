from __future__ import annotations

from pathlib import Path

from .models import QuestionSet
from .paths import slugify
from .website_export import WebsiteQuestionSetV1


def load_questionset(path: Path) -> QuestionSet:
    return QuestionSet.model_validate_json(Path(path).read_text())


def default_filename(qs: QuestionSet, suffix: str = ".json") -> str:
    if qs.curriculum_node_code:
        slug = qs.curriculum_node_code
    else:
        slug = slugify(qs.topic, max_len=40, fallback="questions")
    date = qs.generated_at.strftime("%Y-%m-%d")
    return f"{slug}_{date}{suffix}"


def _resolve_path(qs: QuestionSet, path: Path, suffix: str) -> Path:
    """Resolve a save path: if no suffix, treat as directory and generate a filename."""
    path = Path(path)
    if not path.suffix:
        path.mkdir(parents=True, exist_ok=True)
        return path / default_filename(qs, suffix)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def save_json(qs: QuestionSet, path: Path) -> Path:
    path = _resolve_path(qs, path, ".json")
    path.write_text(qs.model_dump_json(indent=2))
    return path


def save_website_export(web_qs: WebsiteQuestionSetV1, path: Path) -> Path:
    """Save a website export JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(web_qs.model_dump_json(indent=2))
    return path


def save_markdown(qs: QuestionSet, path: Path) -> Path:
    path = Path(path)
    if path.suffix and path.suffix.lower() != ".md":
        path = path.with_suffix(".md")
    path = _resolve_path(qs, path, ".md")
    body = "\n\n---\n\n".join(q.to_md() for q in qs.questions)
    header = f"# {qs.topic}\n\nGenerated: {qs.generated_at.strftime('%Y-%m-%d')}  |  Model: {qs.model}\n\n---\n\n"
    path.write_text(header + body)
    return path
