from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path

from pydantic_ai import Agent, RunContext
from pydantic_ai.usage import RunUsage

from .embed import EmbedClient
from .models import CurriculumNode, CritiqueResult, QuestionSet

_BASE = """\
You write single-best answer (SBA) questions for postgraduate medical examinations.
Questions must be in British English. Use a variety of patient ages and genders where relevant.

## Question structure

Each question has four components:

- Stem: scene-setting text that must NOT itself contain a question. The stem may be:
  - A clinical scenario with a specific patient (include relevant details: age,
    presentation, observations, drug doses, investigation results).
  - A pure scientific, physiological, pharmacological, or physical setup with no patient
    (e.g. "In an experimental situation…", "At atmospheric pressure…", "A drug has the
    following properties…"). Use this form when the topic is better served by a
    direct scientific framing than a contrived patient story.
  Choose whichever form makes the topic most concrete and testable.

- Lead-in: a single, clearly worded question. Must be positively framed — never use
  "which of the following is NOT…" or "EXCEPT". Write the lead-in that most naturally
  fits the stem; do not force a fixed template. It should be specific enough that a
  candidate knows exactly what is being asked without reading the options.

- Options: exactly 5. Exactly one is correct; the other four are plausible distractors.
  Each option carries its own explanation — why it is correct or why it is wrong.
  All five explanations must be completed.

- Explanation: a brief overall explanation of the key concept. Separate from the
  per-option explanations; should provide broader educational context.

## Writing good distractors

- Homogeneous with each other and the correct answer (all drug names, all mechanisms,
  all numerical values — never a mixture of types).
- Concise: options should be as short as the concept permits. Single-word or brief-phrase
  options are preferred when appropriate — do not pad to create false symmetry.
- Similar in length to each other and the correct answer.
- Plausible at first glance, clearly wrong on reflection.
- Non-overlapping — no two options should be essentially the same concept.

Never use "all of the above", "none of the above", or compound options like "A and C".

## Formatting

- Use British English throughout.
- Units: use negative-exponent notation — L min⁻¹, mg kg⁻¹, mmol L⁻¹, ml h⁻¹.
- Drug doses and physiological values should be specific and numerically precise.

## Using reference material

Use the retrieve tool to find relevant source material before writing questions.
Ground factual claims (drug doses, physiological values, mechanisms) in retrieved
content where possible. If retrieval returns nothing useful, rely on your knowledge
but flag uncertainty in the explanation.
"""

_EXAM_CONTEXT: dict[str, str] = {
    "primary": """\
## Exam context: Primary FRCA

Set questions at the standard appropriate for a doctor who has completed foundation
training and has some anaesthetic experience. The Primary FRCA covers basic sciences
(physiology, pharmacology, physics and clinical measurement, statistics). Questions
should test understanding and application of principles, not clinical decision-making.

- Stems are often short — a brief experimental setup or a single factual statement
  can serve as the stem for a pure-science question.
- Options are frequently terse: a single drug name, a pharmacokinetic parameter,
  a physiological variable, or a brief mechanism. Do not inflate them.
- Distractors should be plausible to a doctor with limited anaesthetic exposure.
""",
    "final": """\
## Exam context: Final FRCA

Set questions at the standard appropriate for a senior anaesthetic trainee approaching
independent practice. The Final FRCA covers clinical anaesthesia across all subspecialties
(neuroanaesthesia, obstetrics, paediatrics, ICM, pain, regional, cardiac, thoracic).
Questions should require integration of knowledge and sound clinical judgement.

- Stems typically present complex, realistic clinical scenarios with detailed context
  (monitoring data, drug history, investigation results, comorbidities).
- Options tend to be fuller clinical phrases or management steps rather than single words.
- Questions may draw on landmark studies, NAP reports, and current college guidelines.
- Distractors must be plausible to an experienced trainee — superficially reasonable
  but identifiably wrong to a candidate with genuine subspecialty knowledge.
""",
}


def _build_role(exam: str | None) -> str:
    """Compose the system prompt from the shared base and an exam-specific block."""
    context = _EXAM_CONTEXT.get(exam or "", "")
    return _BASE + ("\n" + context if context else "")

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
        parts = [_build_role(ctx.deps.exam)]

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


async def critique_questions(qs: QuestionSet, model: str) -> tuple[CritiqueResult, RunUsage]:
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
    return result.output, result.usage()


_CONVERT_ROLE = """\
You convert unstructured SBA (single best answer) question text into structured JSON format
for the Royal College of Anaesthetists' FRCA examinations.

For each question in the input:
- stem: the clinical scenario / scene-setting text. Must NOT itself contain a question.
  If the input has no separate stem (question starts directly), use a brief contextual
  restatement as the stem.
- lead: the single lead-in question (positively framed).
- options: exactly 5 options, each with:
    - text: the option text (strip any leading letter/prefix like "A.", "B.")
    - is_correct: true for the correct answer, false for all others
    - explanation: why this option is correct or why it is wrong. If not given in the
      input, generate a concise medically accurate explanation (1–2 sentences).
- explanation: an overall explanation of the key concept. Use the source text if
  provided; otherwise generate one from context.

Rules:
- Every question must have exactly 5 options and exactly 1 correct.
- Strip option letter prefixes (A, B, C, D, E) from option text.
- If the input has fewer or more than 5 options for a question, do your best to infer
  the correct 5 (e.g. if one is split across lines).
- SKIP any question that references an image, ECG, X-ray, chart, or figure that is not
  present in the text (e.g. "His ECG is shown below", "shown in the image"). Do not
  include such questions in the output at all.
- Use the topic provided as the QuestionSet topic field.
- Set exam from the input if identifiable (e.g. "Primary FRCA"), otherwise null.
- Set curriculum_node_codes to an empty list.
- Set model to the model string provided.
"""


async def convert_questions(text: str, topic: str, model: str) -> tuple[QuestionSet, RunUsage]:
    """Parse unstructured SBA question text into a QuestionSet."""
    ag: Agent[None, QuestionSet] = Agent(
        model=model,
        output_type=QuestionSet,
        system_prompt=_CONVERT_ROLE,
        retries=2,
        defer_model_check=True,
    )
    prompt = (
        f"Topic: {topic!r}\n\n"
        f"Parse the following SBA question(s) into a QuestionSet. "
        f"Generate per-option explanations for any that are missing.\n\n"
        f"{text}"
    )
    result = await ag.run(prompt)
    qs = result.output
    qs.topic = topic
    qs.model = model
    qs.questions = [q.with_sorted_options() for q in qs.questions]
    return qs, result.usage()


def _strip_tool_results(messages: list) -> list:
    """Replace tool return content with a placeholder to reduce token usage.

    Preserves the structural few-shot signal (tool was called, response was
    produced) without sending full retrieved document chunks on every request.
    """
    from pydantic_ai.messages import ModelRequest, ToolReturnPart

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
    import numpy as np
    from .curriculum import _make_embedder

    embedder = _make_embedder()
    texts = [topic] + [e["topic"] for e in candidates]
    vecs = np.array(embedder.compute_source_embeddings(texts), dtype=float)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    vecs /= np.where(norms > 0, norms, 1.0)
    sims = vecs[1:] @ vecs[0]
    top_idx = sims.argsort()[::-1][:n]
    return [candidates[i] for i in top_idx]


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
    from pydantic_ai.messages import ModelMessagesTypeAdapter

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

    index: list[dict] = _json.loads(index_path.read_text())

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
        except Exception:
            pass
    return _strip_tool_results(messages)
