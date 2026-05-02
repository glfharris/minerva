from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path

from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelRequest, ToolReturnPart

from .console import console
from .embed import EmbedClient
from .models import CurriculumNode, QuestionSet
from .prompts import build_generation_role

_RAG_THRESHOLD = 0.2  # minimum cosine similarity for a retrieved chunk to be included


@dataclass
class Deps:
    retriever: EmbedClient
    curriculum_path: list[CurriculumNode] = field(default_factory=list)
    exam: str | None = None
    verbose: bool = False


def make_agent(model: str) -> Agent[Deps, QuestionSet]:
    """Create a Pydantic AI agent for the given model string."""
    ag: Agent[Deps, QuestionSet] = Agent(
        model=model,
        deps_type=Deps,
        output_type=QuestionSet,
        retries=2,
        defer_model_check=True,
    )

    @ag.system_prompt
    def build_system_prompt(ctx: RunContext[Deps]) -> str:
        parts = [build_generation_role(ctx.deps.exam)]

        if ctx.deps.curriculum_path:
            chain = " → ".join(n.label for n in ctx.deps.curriculum_path)
            node = ctx.deps.curriculum_path[-1]
            parts.append(
                f"\nCurriculum context:\n"
                f"  Path: {chain}\n"
                f"  Code: {node.code}\n"
            )
            parts.append(
                f"\n## Retrieval\n\n"
                f"Your first call to retrieve must use this query: {chain!r}\n"
                f"You may follow up with more specific queries if needed."
            )

        return "\n".join(parts)

    @ag.tool
    async def retrieve(ctx: RunContext[Deps], query: str) -> str:
        """Search the reference document store for relevant material.

        Formulate query as a specific clinical or pharmacological phrase,
        e.g. 'rocuronium mechanism of action at neuromuscular junction' rather
        than just 'rocuronium'. Prefer one focused query over multiple broad ones.
        Call this before writing each question to ground factual claims in source
        material.
        """
        result = ctx.deps.retriever.query(query, threshold=_RAG_THRESHOLD)
        if ctx.deps.verbose:
            if not result:
                console.print(f"[yellow]No relevant chunks found for query: {query!r}[/yellow]")
            else:
                chunk_count = result.count("---") + 1
                console.print(f"[dim]Retrieved {chunk_count} chunk(s) for query: {query!r}[/dim]")
        return result

    return ag


def _strip_tool_results(messages: list) -> list:
    """Replace tool return content with a placeholder to reduce token usage.

    Preserves the structural few-shot signal (tool was called, response was
    produced) without sending full retrieved document chunks on every request.
    """
    result = []
    for msg in messages:
        if isinstance(msg, ModelRequest):
            new_parts = [
                dataclasses.replace(part, content="[Retrieved reference material]")
                if isinstance(part, ToolReturnPart)
                else part
                for part in msg.parts
            ]
            result.append(dataclasses.replace(msg, parts=new_parts))
        else:
            result.append(msg)
    return result


def _select_by_similarity(candidates: list[dict], topic: str, n: int) -> list[dict]:
    """Return top-n candidates ranked by cosine similarity to topic."""
    from .curriculum import _make_embedder
    from .similarity import rank_by_similarity

    embedder = _make_embedder()
    return [
        candidate
        for _, candidate in rank_by_similarity(
            topic,
            candidates,
            text=lambda entry: entry["topic"],
            embedder=embedder,
            n=n,
        )
    ]


def load_example_messages(
    path: Path | None = None,
    topic: str | None = None,
    exam: str | None = None,
    n: int = 3,
) -> list:
    """Load few-shot message histories filtered by exam and ranked by topic similarity.

    Falls back to loading all files if no index.json exists (legacy behaviour).
    """
    import json as _json

    if path is None:
        path = Path(__file__).parent.parent / "examples" / "histories"
    if not path.exists():
        return []

    index_path = path / "index.json"

    if not index_path.exists():
        # Legacy fallback: load everything
        messages = []
        for f in sorted(path.glob("*.json")):
            try:
                messages.extend(ModelMessagesTypeAdapter.validate_json(f.read_bytes()))
            except Exception:
                pass
        return _strip_tool_results(messages)

    try:
        index: list[dict] = _json.loads(index_path.read_text())
    except Exception as e:
        console.log(
            "[yellow]Warning: could not read example index "
            f"({e}); using no examples.[/yellow]"
        )
        return []

    # Filter by exam; entries with no exam recorded are always included
    candidates = [e for e in index if not e.get("exam") or e.get("exam") == exam] if exam else index

    if not candidates:
        return []

    if topic and len(candidates) > n:
        selected = _select_by_similarity(candidates, topic, n)
    elif len(candidates) > n:
        import random
        selected = random.sample(candidates, n)
    else:
        selected = candidates

    messages = []
    for entry in selected:
        f = path / entry["file"]
        try:
            messages.extend(ModelMessagesTypeAdapter.validate_json(f.read_bytes()))
        except Exception as e:
            console.log(f"[yellow]Warning: could not load example history {f.name} ({e})[/yellow]")
    return _strip_tool_results(messages)
