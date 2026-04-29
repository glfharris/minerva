from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from .models import CurriculumNode

_DATA_DIR = Path(__file__).parent.parent / "data"


def load(exam: Literal["primary", "final"]) -> CurriculumNode:
    """Load a curriculum tree from JSON. Returns the root node."""
    path = _DATA_DIR / f"{exam}_frca.json"
    with open(path) as f:
        data = json.load(f)
    return CurriculumNode.model_validate(data)


def flatten(root: CurriculumNode) -> list[CurriculumNode]:
    """Return all nodes in depth-first order (excluding the synthetic root)."""
    result: list[CurriculumNode] = []

    def _walk(node: CurriculumNode) -> None:
        if node.code != "root":
            result.append(node)
        for child in node.children:
            _walk(child)

    _walk(root)
    return result


def search(nodes: list[CurriculumNode], query: str) -> list[CurriculumNode]:
    """Case-insensitive substring match on code or label."""
    q = query.lower()
    return [n for n in nodes if q in n.code.lower() or q in n.label.lower()]
