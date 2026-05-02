from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.usage import RunUsage

from .models import CritiqueResult, Question, QuestionSet

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


def apply_critique_result(critique_result: CritiqueResult, original_questions: list[Question]) -> list[Question]:
    """Validate and apply a critique result, preserving question ordering."""
    if len(critique_result.critiqued) != len(original_questions):
        raise ValueError(
            "Critique returned "
            f"{len(critique_result.critiqued)} question(s) for {len(original_questions)} input question(s)"
        )
    return [cq.question.with_sorted_options() for cq in critique_result.critiqued]
