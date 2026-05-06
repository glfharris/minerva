from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from .models import CurriculumDocument, CurriculumNode

if TYPE_CHECKING:
    from .models import Question

_DATA_DIR = Path(__file__).parent.parent / "data"
EMBED_MODEL = "NeuML/pubmedbert-base-embeddings"
_MATCH_THRESHOLD = 0.4  # cosine similarity; below this = no confident match

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


def normalize_assessment_key(exam: str | None) -> AssessmentKey | None:
    if exam is None:
        return None
    return ASSESSMENT_ALIASES.get(str(exam))


def curriculum_stem(exam: str) -> CurriculumStem | None:
    assessment = normalize_assessment_key(exam)
    return CURRICULUM_STEM_BY_ASSESSMENT.get(assessment) if assessment else None


def l2_to_cosine(d: float) -> float:
    """Convert LanceDB L2 distance to cosine similarity for normalised vectors."""
    return 1 - (d ** 2 / 2)


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


def _make_embedder():
    from .embed import _make_embedder as _make_embedder_cached
    return _make_embedder_cached(f"sentence-transformers:{EMBED_MODEL}")


def _make_node_model(embedder):
    from lancedb.pydantic import LanceModel, Vector

    class CurriculumNodeRecord(LanceModel):
        code: str
        label: str
        text: str = embedder.SourceField()
        vector: Vector(embedder.ndims()) = embedder.VectorField()

    return CurriculumNodeRecord


def _get_table(db, exam: str):
    """Return the curriculum LanceDB table, building it if it doesn't exist."""
    from .console import console

    stem = curriculum_stem(exam)
    if stem is None:
        raise ValueError(f"Unknown exam: {exam!r}")
    table_name = f"curriculum_{stem}"
    embedder = _make_embedder()
    Model = _make_node_model(embedder)

    if table_name in db.table_names():
        return db.open_table(table_name), Model

    root = load(exam)
    nodes = flatten(root)
    node_map, parent_map = _build_maps(root)

    console.print(f"Building curriculum embeddings for {stem} FRCA (one-time)…")
    records = [
        {
            "code": n.code,
            "label": n.label,
            "text": _build_text(n.code, node_map, parent_map),
        }
        for n in nodes
    ]

    table = db.create_table(table_name, schema=Model)
    table.add(records)
    console.print(f"Embedded {len(records)} curriculum nodes into '{table_name}'")

    return table, Model


def _open_table(exam: str, db_path: str | Path):
    import lancedb
    db = lancedb.connect(str(db_path))
    return _get_table(db, exam)


def search_table(
    topic: str,
    exam: str,
    db_path: str | Path = "./lancedb",
    n: int = 5,
):
    """Return top-n matches as (similarity, CurriculumNode) pairs."""
    table, _ = _open_table(exam, db_path)

    results = table.search(topic).limit(n).to_pandas()
    root = load(exam)
    node_map, _ = _build_maps(root)

    return [
        (l2_to_cosine(float(row["_distance"])), node_map[row["code"]])
        for _, row in results.iterrows()
        if row["code"] in node_map
    ]


def match_question_nodes(
    question: Question,
    exam: str | None,
    db_path: str | Path = "./lancedb",
    n: int = 5,
    threshold: float = _MATCH_THRESHOLD,
) -> list[tuple[str, float]]:
    """Return (code, similarity) pairs that best match a question's content.

    Builds a query from the question's full text (stem, lead-in, correct option
    explanation, overall explanation) and returns all matches with cosine similarity
    above *threshold*, up to *n* results, ordered by descending similarity.

    If *exam* is None, both primary and final tables are searched and results merged.
    """
    query = " ".join([
        question.stem,
        question.lead,
        question.correct_option.explanation,
        question.explanation,
    ])
    normalized = normalize_assessment_key(exam)
    exams = (normalized,) if normalized else _ASSESSMENT_SEARCH_ORDER
    merged: list[tuple[float, CurriculumNode]] = []
    failures: list[str] = []
    for ex in exams:
        try:
            merged.extend(search_table(query, ex, db_path=db_path, n=n))
        except Exception as e:
            failures.append(f"{ex}: {e}")
    if failures and not merged:
        from .console import console
        console.log(
            "[yellow]Warning: could not match curriculum nodes "
            f"({'; '.join(failures)})[/yellow]"
        )
    merged.sort(key=lambda x: x[0], reverse=True)
    return [(node.code, score) for score, node in merged if score >= threshold][:n]


def rematch_questions(questions: list[Question], exam: str | None, db_path: str | Path) -> None:
    """Replace each question's curriculum node codes and scores with semantic matches."""
    for q in questions:
        matches = match_question_nodes(q, exam, db_path=db_path)
        q.curriculum_node_codes = [code for code, _ in matches]
        q.curriculum_node_scores = [score for _, score in matches]
