from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from .models import CurriculumNode

if TYPE_CHECKING:
    from .models import Question

_DATA_DIR = Path(__file__).parent.parent / "data"
EMBED_MODEL = "NeuML/pubmedbert-base-embeddings"
_MATCH_THRESHOLD = 0.4  # cosine similarity; below this = no confident match


def l2_to_cosine(d: float) -> float:
    """Convert LanceDB L2 distance to cosine similarity for normalised vectors."""
    return 1 - (d ** 2 / 2)


@lru_cache(maxsize=None)
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


def _get_table(db, exam: Literal["primary", "final"]):
    """Return the curriculum LanceDB table, building it if it doesn't exist."""
    from .console import console

    table_name = f"curriculum_{exam}"
    embedder = _make_embedder()
    Model = _make_node_model(embedder)

    if table_name in db.table_names():
        return db.open_table(table_name), Model

    root = load(exam)
    nodes = flatten(root)
    node_map, parent_map = _build_maps(root)

    console.log(f"Building curriculum embeddings for {exam} FRCA (one-time)…")
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
    console.log(f"Embedded {len(records)} curriculum nodes into '{table_name}'")

    return table, Model


def _open_table(exam: Literal["primary", "final"], db_path: str | Path):
    import lancedb
    db = lancedb.connect(str(db_path))
    return _get_table(db, exam)


def match_topic(
    topic: str,
    exam: Literal["primary", "final"],
    db_path: str | Path = "./lancedb",
    threshold: float = _MATCH_THRESHOLD,
) -> CurriculumNode | None:
    """Embed topic and return the best-matching curriculum node, or None if below threshold."""
    table, _ = _open_table(exam, db_path)

    # LanceDB uses L2 distance on normalised vectors; cosine similarity = 1 - (d² / 2)
    results = table.search(topic).limit(1).to_pandas()
    if results.empty:
        return None

    best = results.iloc[0]
    similarity = l2_to_cosine(float(best["_distance"]))

    if similarity < threshold:
        return None

    root = load(exam)
    node_map, _ = _build_maps(root)
    return node_map.get(best["code"])


def search_table(
    topic: str,
    exam: Literal["primary", "final"],
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
    exam: Literal["primary", "final"] | None,
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
    exams: tuple[Literal["primary", "final"], ...] = (exam,) if exam else ("primary", "final")
    merged: list[tuple[float, CurriculumNode]] = []
    for ex in exams:
        try:
            merged.extend(search_table(query, ex, db_path=db_path, n=n))
        except Exception:
            pass
    merged.sort(key=lambda x: x[0], reverse=True)
    return [(node.code, score) for score, node in merged if score >= threshold][:n]
