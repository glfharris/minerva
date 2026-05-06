from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from .models import CurriculumDocument, CurriculumNode

_DATA_DIR = Path(__file__).parent.parent / "data"

AssessmentKey = Literal["primary_frca", "final_frca"]
CurriculumStem = Literal["primary", "final"]

ASSESSMENT_ALIASES: dict[str, AssessmentKey] = {
    "primary": "primary_frca",
    "primary_frca": "primary_frca",
    "final": "final_frca",
    "final_frca": "final_frca",
}
CURRICULUM_STEM_BY_ASSESSMENT: dict[AssessmentKey, CurriculumStem] = {
    "primary_frca": "primary",
    "final_frca": "final",
}
ASSESSMENT_BY_CURRICULUM_STEM: dict[CurriculumStem, AssessmentKey] = {
    "primary": "primary_frca",
    "final": "final_frca",
}
_ASSESSMENT_SEARCH_ORDER: tuple[AssessmentKey, AssessmentKey] = ("primary_frca", "final_frca")


@dataclass(frozen=True)
class ResolvedTopic:
    node: CurriculumNode | None
    exam: AssessmentKey | None
    topic: str


@dataclass(frozen=True)
class QuestionCurriculumAlignment:
    node_code: str
    score: float


@dataclass(frozen=True)
class QuestionCurriculumAlignmentResult:
    alignments: list[QuestionCurriculumAlignment]

    @classmethod
    def from_node_matches(
        cls,
        matches: list[tuple[str, float]],
    ) -> QuestionCurriculumAlignmentResult:
        return cls([
            QuestionCurriculumAlignment(node_code=code, score=score)
            for code, score in matches
        ])

    @classmethod
    def from_question(
        cls,
        question: Question,
    ) -> QuestionCurriculumAlignmentResult:
        return cls([
            QuestionCurriculumAlignment(node_code=code, score=score)
            for code, score in zip(
                question.curriculum_node_codes,
                question.curriculum_node_scores,
                strict=True,
            )
        ])

    @property
    def node_codes(self) -> list[str]:
        return [alignment.node_code for alignment in self.alignments]

    @property
    def scores(self) -> list[float]:
        return [alignment.score for alignment in self.alignments]

    def apply_to(self, question: Question) -> None:
        question.curriculum_node_codes = self.node_codes
        question.curriculum_node_scores = self.scores


def normalize_assessment_key(exam: str | None) -> AssessmentKey | None:
    if exam is None:
        return None
    return ASSESSMENT_ALIASES.get(str(exam))


def curriculum_stem(exam: str) -> CurriculumStem | None:
    assessment = normalize_assessment_key(exam)
    return CURRICULUM_STEM_BY_ASSESSMENT.get(assessment) if assessment else None


@lru_cache(maxsize=None)
def load_document(exam: str) -> CurriculumDocument | None:
    """Load curriculum metadata and tree from JSON, when using the wrapped schema."""
    stem = curriculum_stem(exam)
    if stem is None:
        raise ValueError(f"Unknown exam: {exam!r}")
    path = _DATA_DIR / f"{stem}_frca.json"
    with open(path) as f:
        data = json.load(f)
    if "root" not in data:
        return None
    return CurriculumDocument.model_validate(data)


@lru_cache(maxsize=None)
def load(exam: str) -> CurriculumNode:
    """Load a curriculum tree from JSON. Returns the root node."""
    stem = curriculum_stem(exam)
    if stem is None:
        raise ValueError(f"Unknown exam: {exam!r}")
    path = _DATA_DIR / f"{stem}_frca.json"
    with open(path) as f:
        data = json.load(f)
    if "root" in data:
        return CurriculumDocument.model_validate(data).root
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
    """Return nodes whose code or label contains the query, case-insensitively."""
    q = query.casefold()
    return [
        node for node in nodes
        if q in node.code.casefold() or q in node.label.casefold()
    ]


def node_path(root: CurriculumNode, code: str) -> list[CurriculumNode]:
    """Return the list of nodes from root to the node with the given code (root excluded)."""
    def _find(node: CurriculumNode, path: list[CurriculumNode]) -> list[CurriculumNode] | None:
        current_path = path + ([node] if node.code != "root" else [])
        if node.code == code:
            return current_path
        for child in node.children:
            result = _find(child, current_path)
            if result is not None:
                return result
        return None

    return _find(root, []) or []


def lookup_node(exam: str | None, code: str) -> tuple[CurriculumNode, str] | None:
    """Look up a curriculum node by exact code, inferring exam when omitted."""
    normalized = normalize_assessment_key(exam)
    exams_to_search = (normalized,) if normalized else _ASSESSMENT_SEARCH_ORDER
    for ex in exams_to_search:
        path = node_path(load(ex), code)
        if path:
            return path[-1], ex
    return None


def resolve_topic(exam: str | None, node_code: str | None, topic: str | None) -> ResolvedTopic | None:
    """Resolve optional node code and topic into generation context."""
    exam = normalize_assessment_key(exam)
    curriculum_node: CurriculumNode | None = None
    if node_code:
        result = lookup_node(exam, node_code)
        if result is None:
            return None
        curriculum_node, exam = result
    if not topic:
        if curriculum_node:
            topic = curriculum_node.label
        else:
            return None
    return ResolvedTopic(node=curriculum_node, exam=exam, topic=topic)


def _build_maps(root: CurriculumNode) -> tuple[dict[str, CurriculumNode], dict[str, str]]:
    """Single-pass tree walk returning (code→node, child_code→parent_code)."""
    node_map: dict[str, CurriculumNode] = {}
    parent_map: dict[str, str] = {}

    def _walk(node: CurriculumNode) -> None:
        node_map[node.code] = node
        for child in node.children:
            parent_map[child.code] = node.code
            _walk(child)

    _walk(root)
    return node_map, parent_map


def _build_text(code: str, node_map: dict[str, CurriculumNode], parent_map: dict[str, str]) -> str:
    """Walk up the parent chain to build a rich label, mirroring minerva-server."""
    parts = []
    current_code = code
    while current_code and current_code != "root":
        node = node_map.get(current_code)
        if node:
            parts.append(node.label)
        current_code = parent_map.get(current_code, "")
    parts.reverse()
    return ". ".join(parts)


