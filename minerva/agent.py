from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pydantic_ai import Agent, RunContext

from .embed import EmbedClient
from .models import CurriculumNode, QuestionSet

_ROLE = """\
You write single-best answer (SBA) questions for the Royal College of Anaesthetists'
Primary FRCA examination. Questions must be in British English, set at the standard
appropriate for a doctor who has completed foundation training and has some anaesthetic
experience. Use a variety of patient ages and genders where relevant.

## Question structure

Each question has four components:

- Stem: a specific, realistic clinical scenario. Must NOT itself contain a question.
  Include relevant details (age, presentation, observations, drug doses) — avoid vague
  generalities. The scenario should make the topic concrete and clinically grounded.

- Lead-in: a single, clearly worded question. Must be positively framed — never use
  "which of the following is NOT…" or "EXCEPT".

- Options: exactly 5, labelled A–E. Exactly one is correct; the other four are
  distractors.

- Options: each option carries its own explanation — why it is correct (for the right
  answer) or why it is wrong (for each distractor). Must be completed for all five options.

- Explanation: a brief overall explanation of the key concept being tested and any
  important related points. This is separate from the per-option explanations and
  should provide broader educational context.

## Writing good distractors

Distractors are the hardest part of SBA writing. They must be:
- Plausible to a doctor with limited anaesthetic experience — not obviously absurd
- Homogeneous with each other and the correct answer (e.g. all drug names, all
  mechanisms, all numerical values — never a mixture of types)
- Similar in length to the correct answer — a noticeably longer or shorter option
  signals the correct answer
- Clearly incorrect on reflection, but believable at first glance
- Non-overlapping — no two options should be essentially the same

Never use "all of the above", "none of the above", or compound options like "A and C".

## Using reference material

Use the retrieve tool to find relevant source material before writing questions.
Ground factual claims (drug doses, physiological values, mechanisms) in retrieved
content where possible. If retrieval returns nothing useful, rely on your knowledge
but flag uncertainty in the explanation.
"""

_RAG_THRESHOLD = 0.3  # minimum cosine similarity for a retrieved chunk to be included


@dataclass
class Deps:
    retriever: EmbedClient
    curriculum_path: list[CurriculumNode] = field(default_factory=list)
    examples: list[str] | None = None
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
        parts = [_ROLE]

        if ctx.deps.curriculum_path:
            chain = " → ".join(n.label for n in ctx.deps.curriculum_path)
            node = ctx.deps.curriculum_path[-1]
            parts.append(
                f"\nCurriculum context:\n"
                f"  Path: {chain}\n"
                f"  Code: {node.code}\n"
            )

        if ctx.deps.examples:
            examples_text = "\n\n---\n\n".join(ctx.deps.examples[:3])
            parts.append(f"\nHere are example SBA questions for reference:\n\n{examples_text}")

        return "\n".join(parts)

    @ag.tool
    async def retrieve(ctx: RunContext[Deps], query: str) -> str:
        """Retrieve relevant reference material for the given query."""
        from .console import console
        result = ctx.deps.retriever.query(query, threshold=_RAG_THRESHOLD)
        if ctx.deps.verbose:
            if not result:
                console.log(f"[yellow]No relevant chunks found for query: {query!r}[/yellow]")
            else:
                chunk_count = result.count("---") + 1
                console.log(f"[dim]Retrieved {chunk_count} chunk(s) for query: {query!r}[/dim]")
        return result

    return ag


def load_examples(path: Path | None = None) -> list[str]:
    if path is None:
        path = Path(__file__).parent.parent / "examples" / "rcoa.md"
    if not path.exists():
        return []
    return [s.strip() for s in path.read_text().split("---") if s.strip()]
