from __future__ import annotations

import re
from pathlib import Path

from .models import QuestionSet


def default_filename(qs: QuestionSet, suffix: str = ".json") -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", qs.topic.lower()).strip("_")
    date = qs.generated_at.strftime("%Y-%m-%d")
    return f"{slug}_{date}{suffix}"


def save_json(qs: QuestionSet, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_dir():
        path = path / default_filename(qs, ".json")
    path.write_text(qs.model_dump_json(indent=2))
    return path


def save_markdown(qs: QuestionSet, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_dir():
        path = path / default_filename(qs, ".md")
    body = "\n\n---\n\n".join(q.to_md() for q in qs.questions)
    header = f"# {qs.topic}\n\nGenerated: {qs.generated_at.strftime('%Y-%m-%d')}  |  Model: {qs.model}\n\n---\n\n"
    path.write_text(header + body)
    return path
