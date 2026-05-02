from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar

T = TypeVar("T")


def rank_by_similarity(
    query: str,
    items: Sequence[T],
    text: Callable[[T], str],
    embedder,
    n: int,
) -> list[tuple[float, T]]:
    """Rank items by cosine similarity to query using an embedding function."""
    import numpy as np

    if not items:
        return []

    texts = [query] + [text(item) for item in items]
    vecs = np.array(embedder.compute_source_embeddings(texts), dtype=float)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    vecs /= np.where(norms > 0, norms, 1.0)
    sims = (vecs[1:] @ vecs[0]).tolist()
    ranked = sorted(zip(sims, items), key=lambda x: x[0], reverse=True)
    return ranked[:n]
