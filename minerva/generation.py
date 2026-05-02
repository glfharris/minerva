from __future__ import annotations

import random
from dataclasses import dataclass

from pydantic_ai.usage import RunUsage

from .agent import Deps, load_example_messages, make_agent
from .curriculum import _MATCH_THRESHOLD, _make_embedder, flatten, load, node_path
from .embed import EmbedClient
from .models import CurriculumNode, QuestionSet
from .similarity import rank_by_similarity


@dataclass(frozen=True)
class GenerationPlanItem:
    node: CurriculumNode | None
    count: int
    score: float | None = None


def plan_from_candidates(
    candidates: list[tuple[float, CurriculumNode]], count: int
) -> list[GenerationPlanItem]:
    """Build a generation plan from ranked (score, node) candidates."""
    if count == 1:
        score, selected = candidates[0]
        return [GenerationPlanItem(node=selected, count=1, score=score)]

    selected_nodes = [candidates[i % len(candidates)] for i in range(count)]
    random.shuffle(selected_nodes)

    by_code: dict[str, GenerationPlanItem] = {}
    for score, node in selected_nodes:
        existing = by_code.get(node.code)
        by_code[node.code] = GenerationPlanItem(
            node=node,
            count=(existing.count if existing else 0) + 1,
            score=score,
        )

    return list(by_code.values())


def subtree_node_text(root: CurriculumNode, node: CurriculumNode) -> str:
    path = node_path(root, node.code)
    return ". ".join(n.label for n in path) if path else node.label


def rank_subtree(
    root: CurriculumNode, topic: str, n: int = 10
) -> list[tuple[float, CurriculumNode]]:
    """Return top-n descendants of root ranked by cosine similarity to topic."""
    descendants = [node for node in flatten(root) if node.code != root.code]
    embedder = _make_embedder()
    return rank_by_similarity(
        topic,
        descendants,
        text=lambda node: subtree_node_text(root, node),
        embedder=embedder,
        n=n,
    )


def subtree_generation_plan(
    root: CurriculumNode,
    topic: str,
    count: int,
    threshold: float = _MATCH_THRESHOLD,
) -> list[GenerationPlanItem]:
    """Rank descendants within a subtree and fall back to the parent if none match confidently."""
    candidates = [
        (score, node)
        for score, node in rank_subtree(root, topic, n=10)
        if score >= threshold
    ]
    if candidates:
        return plan_from_candidates(candidates, count)
    return [GenerationPlanItem(node=root, count=count)]


def plan_node_codes(plan: list[GenerationPlanItem]) -> set[str]:
    return {item.node.code for item in plan if item.node is not None}


async def generate_questions(
    topic: str,
    count: int,
    model: str,
    exam: str | None,
    node: CurriculumNode | None,
    retriever: EmbedClient,
    verbose: bool = False,
    prior_stems: list[str] | None = None,
) -> tuple[QuestionSet, list, RunUsage]:
    curriculum_path = (
        node_path(load(exam), node.code)  # type: ignore[arg-type]
        if (node and exam)
        else []
    )
    deps = Deps(
        retriever=retriever,
        curriculum_path=curriculum_path,
        exam=exam,
        verbose=verbose,
    )

    prior_clause = ""
    if prior_stems:
        stems_text = "\n\n".join(f"- {s}" for s in prior_stems)
        prior_clause = (
            "\n\nThe following stem(s) have already been written for this question set. "
            "Ensure your patient demographics and clinical presentation are clearly "
            "distinct from these:\n\n"
            f"{stems_text}"
        )
    prompt = (
        f"Write {count} dissimilar SBA question(s) on: {topic!r}.\n\n"
        "Each question should test application of knowledge, not simple recall — "
        "a candidate should need to reason from principles rather than just retrieve a fact. "
        "Use the retrieve tool to find relevant reference material before writing. "
        f"Return the result as a QuestionSet.{prior_clause}"
    )

    ag = make_agent(model)
    example_messages = load_example_messages(topic=topic, exam=exam)

    result = await ag.run(prompt, deps=deps, message_history=example_messages)
    qs = result.output
    qs.topic = topic
    qs.exam = exam
    qs.model = model
    if node:
        qs.curriculum_node_code = node.code
    qs.questions = [q.with_sorted_options() for q in qs.questions]
    return qs, result.all_messages(), result.usage()
