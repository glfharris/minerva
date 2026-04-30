from __future__ import annotations

import re
from pathlib import Path

from .models import QuestionSet


def default_filename(qs: QuestionSet, suffix: str = ".json") -> str:
    if qs.curriculum_node_code:
        slug = qs.curriculum_node_code
    else:
        slug = re.sub(r"[^a-z0-9]+", "_", qs.topic.lower()).strip("_")[:40].strip("_")
    date = qs.generated_at.strftime("%Y-%m-%d")
    return f"{slug}_{date}{suffix}"


def save_json(qs: QuestionSet, path: Path) -> Path:
    path = Path(path)
    if not path.suffix:
        path.mkdir(parents=True, exist_ok=True)
        path = path / default_filename(qs, ".json")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(qs.model_dump_json(indent=2))
    return path


def save_markdown(qs: QuestionSet, path: Path) -> Path:
    path = Path(path)
    if not path.suffix:
        path.mkdir(parents=True, exist_ok=True)
        path = path / default_filename(qs, ".md")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n\n---\n\n".join(q.to_md() for q in qs.questions)
    header = f"# {qs.topic}\n\nGenerated: {qs.generated_at.strftime('%Y-%m-%d')}  |  Model: {qs.model}\n\n---\n\n"
    path.write_text(header + body)
    return path
