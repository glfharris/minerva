from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .curriculum import (
    QuestionCurriculumAlignmentResult,
    _ASSESSMENT_SEARCH_ORDER,
    _build_maps,
    _build_text,
    curriculum_stem,
    flatten,
    load,
    normalize_assessment_key,
)
from .embed import _make_embedder, l2_to_cosine
from .models import CurriculumNode

if TYPE_CHECKING:
    from .models import Question

_MATCH_THRESHOLD = 0.4  # cosine similarity; below this = no confident match


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


def match_question_curriculum(
    question: Question,
    exam: str | None,
    db_path: str | Path = "./lancedb",
    n: int = 5,
    threshold: float = _MATCH_THRESHOLD,
) -> QuestionCurriculumAlignmentResult:
    """Return curriculum alignment matches for a question."""
    return QuestionCurriculumAlignmentResult.from_node_matches(
        match_question_nodes(
            question,
            exam,
            db_path=db_path,
            n=n,
            threshold=threshold,
        )
    )


def rematch_questions(questions: list[Question], exam: str | None, db_path: str | Path) -> None:
    """Replace each question's curriculum node codes and scores with semantic matches."""
    for q in questions:
        match_question_curriculum(q, exam, db_path=db_path).apply_to(q)
