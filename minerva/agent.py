from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pydantic_ai import Agent, RunContext

from .embed import EmbedClient
from .models import CurriculumNode, CritiqueResult, QuestionSet

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

_RAG_THRESHOLD = 0.2  # minimum cosine similarity for a retrieved chunk to be included


@dataclass
class Deps:
    retriever: EmbedClient
    curriculum_path: list[CurriculumNode] = field(default_factory=list)
    examples: list[str] | None = None
    verbose: bool = False
    exam: str | None = None  # set only when agent should use match_curriculum tool
    db_path: Path = field(default_factory=lambda: Path("./lancedb"))


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
                f"\nCurriculum context (explicitly specified — do not call match_curriculum):\n"
                f"  Path: {chain}\n"
                f"  Code: {node.code}\n"
            )
        elif ctx.deps.exam:
            parts.append(
                f"\nUse the match_curriculum tool to find the relevant {ctx.deps.exam} FRCA "
                f"curriculum node before writing questions. Use a specific clinical query, "
                f"not just the bare topic word."
            )

        if ctx.deps.examples:
            examples_text = "\n\n---\n\n".join(ctx.deps.examples[:3])
            parts.append(f"\nHere are example SBA questions for reference:\n\n{examples_text}")

        return "\n".join(parts)

    @ag.tool
    async def match_curriculum(ctx: RunContext[Deps], query: str) -> str:
        """Find the most relevant FRCA curriculum node for the given topic.

        Call this once before writing questions when an exam has been specified.
        Use a specific clinical phrase, e.g. 'sugammadex reversal of neuromuscular
        blockade' rather than just 'sugammadex'. If the result does not look relevant
        to the topic, disregard it.
        """
        from .console import console
        from .curriculum import load, match_topic, node_path

        if not ctx.deps.exam:
            return "No exam specified — curriculum matching unavailable."

        if ctx.deps.verbose:
            console.log(f"[dim]Searching curriculum for: {query!r}[/dim]")

        node = match_topic(query, ctx.deps.exam, db_path=ctx.deps.db_path)  # type: ignore[arg-type]
        if not node:
            if ctx.deps.verbose:
                console.log(f"[yellow]No confident curriculum match for: {query!r}[/yellow]")
            return "No confident curriculum match found — proceed without curriculum context."

        root = load(ctx.deps.exam)  # type: ignore[arg-type]
        path = node_path(root, node.code)
        chain = " → ".join(n.label for n in path)

        if ctx.deps.verbose:
            console.log(f"[dim]Curriculum match: {node.code} — {node.label}[/dim]")

        return f"Curriculum node matched:\n  Path: {chain}\n  Code: {node.code}"

    @ag.tool
    async def retrieve(ctx: RunContext[Deps], query: str) -> str:
        """Search the reference document store for relevant material.

        Formulate query as a specific clinical or pharmacological phrase,
        e.g. 'rocuronium mechanism of action at neuromuscular junction' rather
        than just 'rocuronium'. Prefer one focused query over multiple broad ones.
        Call this before writing each question to ground factual claims in source
        material.
        """
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


_CRITIQUE_ROLE = """\
You are an expert SBA (single best answer) question editor for the Royal College of \
Anaesthetists' FRCA examinations. You receive a set of draft questions and return a \
revised version with per-question feedback.

For each question, check the following and correct any failures:

1. **Positive framing** — lead-in must not use "NOT", "EXCEPT", or "LEAST". Rewrite if needed.
2. **Homogeneous options** — all five options must be the same type (all drug names, all \
mechanisms, all numerical values, etc.). Replace any outlier distractors.
3. **Similar option length** — no option should be conspicuously longer or shorter than \
the others. Pad or trim as needed.
4. **Plausible distractors** — each distractor must be believable to a doctor with limited \
anaesthetic experience. Replace any obviously absurd distractors.
5. **Distinct options** — no two options should be essentially the same concept. Replace \
duplicates.
6. **Per-option explanations** — every option must have a complete explanation (why correct \
or why wrong). Fill in any that are missing or too brief.
7. **Overall explanation** — must provide broader educational context beyond the per-option \
text. Expand if it merely restates the correct answer.
8. **Clinical accuracy** — correct any factual errors you are confident about.

For each question return:
- `feedback`: a concise summary of what was changed and why. If nothing needed changing, \
write exactly "No changes needed."
- `question`: the full revised question, copied exactly and unchanged if no edits were required.

## Important

"No changes needed." is a completely valid and expected outcome. Most well-written questions \
will pass all criteria without any edits. Do not invent corrections, reword things \
unnecessarily, or claim a change was made unless the original genuinely failed one of the \
criteria above. Fabricating a correction is worse than saying nothing. If in doubt, leave \
the question unchanged and write "No changes needed."
"""


async def critique_questions(qs: QuestionSet, model: str) -> CritiqueResult:
    """Run a critique pass on a generated QuestionSet and return revised questions with feedback."""
    ag: Agent[None, CritiqueResult] = Agent(
        model=model,
        output_type=CritiqueResult,
        system_prompt=_CRITIQUE_ROLE,
        retries=2,
        defer_model_check=True,
    )
    prompt = (
        f"Review and improve the following {len(qs.questions)} SBA question(s). "
        f"Return one CritiquedQuestion per input question, in the same order.\n\n"
        f"{qs.model_dump_json(indent=2)}"
    )
    result = await ag.run(prompt)
    return result.output


def load_example_messages(path: Path | None = None) -> list:
    """Load saved few-shot message histories from examples/histories/."""
    from pydantic_ai.messages import ModelMessagesTypeAdapter
    if path is None:
        path = Path(__file__).parent.parent / "examples" / "histories"
    if not path.exists():
        return []
    messages = []
    for f in sorted(path.glob("*.json")):
        try:
            messages.extend(ModelMessagesTypeAdapter.validate_json(f.read_bytes()))
        except Exception:
            pass  # skip malformed files
    return messages
