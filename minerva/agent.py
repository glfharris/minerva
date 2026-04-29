from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic_ai import Agent, RunContext

from .embed import EmbedClient
from .models import CurriculumNode, QuestionSet

_ROLE = """\
You write single-best answer (SBA) questions for the Royal College of Anaesthetists'
Primary FRCA examination. Questions must be in British English and set at a standard
appropriate for doctors with some anaesthetic experience. Use a variety of patient ages
and genders where relevant.

An SBA question has:
- A Stem: scene-setting text that does NOT itself contain a question
- A Lead-in: the actual question to answer
- Exactly 5 options labelled A–E, of which exactly one is correct
- An explanation of the correct answer
"""


@dataclass
class Deps:
    retriever: EmbedClient
    curriculum_node: CurriculumNode | None = None
    examples: list[str] | None = None


def make_agent(model: str) -> Agent[Deps, QuestionSet]:
    """Create a Pydantic AI agent for the given model string."""
    ag: Agent[Deps, QuestionSet] = Agent(
        model=model,
        deps_type=Deps,
        result_type=QuestionSet,
        retries=2,
    )

    @ag.system_prompt
    def build_system_prompt(ctx: RunContext[Deps]) -> str:
        parts = [_ROLE]
        if ctx.deps.curriculum_node:
            node = ctx.deps.curriculum_node
            parts.append(
                f"\nCurriculum context:\n"
                f"  Code: {node.code}\n"
                f"  Topic: {node.label}\n"
            )
        if ctx.deps.examples:
            examples_text = "\n\n---\n\n".join(ctx.deps.examples[:3])
            parts.append(f"\nHere are example SBA questions for reference:\n\n{examples_text}")
        return "\n".join(parts)

    @ag.tool
    async def retrieve(ctx: RunContext[Deps], query: str) -> str:
        """Retrieve relevant reference material for the given query."""
        return ctx.deps.retriever.query(query)

    return ag


def load_examples(path: Path | None = None) -> list[str]:
    if path is None:
        path = Path(__file__).parent.parent / "examples" / "rcoa.md"
    if not path.exists():
        return []
    return [s.strip() for s in path.read_text().split("---") if s.strip()]
