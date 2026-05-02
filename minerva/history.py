from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .console import console
from .output import load_questionset
from .paths import slugify


def first_sentence(text: str) -> str:
    """Extract the first sentence from a block of text."""
    for sep in (". ", ".\n"):
        idx = text.find(sep)
        if idx != -1:
            return text[: idx + 1].strip()
    return text.strip()[:200]


def make_history_files(files: list[Path], output: Path) -> None:
    from pydantic_ai.messages import (
        ModelMessagesTypeAdapter,
        ModelRequest,
        ModelResponse,
        ToolCallPart,
        ToolReturnPart,
        UserPromptPart,
    )

    output.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)

    index_path = output / "index.json"
    index: dict[str, dict] = {}
    if index_path.exists():
        for entry in json.loads(index_path.read_text()):
            index[entry["file"]] = entry

    for file in files:
        try:
            qs = load_questionset(file)
        except Exception as e:
            console.print(f"[red]Could not load '{file}': {e}[/red]")
            continue

        saved = 0
        for q in qs.questions:
            topic = q.title or first_sentence(q.explanation)
            slug = slugify(topic, max_len=50, fallback="question")
            filename = f"{slug}.json"
            retrieve_id = f"mock_r_{slug[:12]}"
            final_id = f"mock_f_{slug[:12]}"

            single_qs = qs.model_copy(update={"questions": [q]})
            prompt = (
                f"Write 1 dissimilar SBA question(s) on: {topic!r}.\n\n"
                "Each question should test application of knowledge, not simple recall — "
                "a candidate should need to reason from principles rather than just retrieve a fact. "
                "Use the retrieve tool to find relevant reference material before writing. "
                "Return the result as a QuestionSet."
            )

            messages = [
                ModelRequest(parts=[UserPromptPart(content=prompt, timestamp=now)], timestamp=now),
                ModelResponse(parts=[ToolCallPart(tool_name="retrieve", args=f'{{"query": {topic!r}}}', tool_call_id=retrieve_id)], timestamp=now),
                ModelRequest(parts=[ToolReturnPart(tool_name="retrieve", content="[Retrieved reference material]", tool_call_id=retrieve_id, timestamp=now)], timestamp=now),
                ModelResponse(parts=[ToolCallPart(tool_name="final_result", args=single_qs.model_dump_json(), tool_call_id=final_id)], timestamp=now),
                ModelRequest(parts=[ToolReturnPart(tool_name="final_result", content="Final result processed.", tool_call_id=final_id, timestamp=now)], timestamp=now),
            ]

            (output / filename).write_bytes(ModelMessagesTypeAdapter.dump_json(messages))
            index[filename] = {"file": filename, "exam": qs.exam, "topic": topic}
            saved += 1

        console.print(f"[green]Saved {saved} example(s) from {file.name}[/green]")

    index_path.write_text(json.dumps(list(index.values()), indent=2))
    console.print(f"[green]Index:[/green] {index_path} ({len(index)} entries)")
