from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.usage import RunUsage

from .models import QuestionSet

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
- title: a short topic label (5–10 words) capturing the key concept, e.g.
  "Rocuronium — mechanism at the NMJ". Written as a label, not a question.

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
