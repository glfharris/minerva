#! uv run
"""Retitle history files: generate proper short titles for each question,
rename the file, patch the title into final_result args, update index.json."""
from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from pydantic_ai import Agent

load_dotenv()

HISTORIES_DIR = Path("examples/histories")
MODEL = os.environ.get("MINERVA_MODEL", "openai:gpt-4o")

_TITLE_ROLE = """\
Generate a concise topic label (5–10 words) for the SBA question provided.
Written as a descriptive label — not a question — using the style:
  "Rocuronium — mechanism at the NMJ"
  "One-lung ventilation — hypoxic pulmonary vasoconstriction"
  "Adrenaline — mechanism of hyperglycaemia"
Return only the title label, nothing else.
"""

_ag: Agent[None, str] = Agent(
    model=MODEL,
    output_type=str,
    system_prompt=_TITLE_ROLE,
    defer_model_check=True,
)


async def _generate_title(q: dict) -> str:
    prompt = (
        f"Stem: {q.get('stem', '')}\n\n"
        f"Lead: {q.get('lead', '')}\n\n"
        f"Explanation: {q.get('explanation', '')}"
    )
    result = await _ag.run(prompt)
    return result.output.strip()


def _slug(title: str, max_len: int = 60) -> str:
    return re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:max_len]


def _extract_question(messages: list) -> dict | None:
    for msg in messages:
        if msg.get("kind") != "response":
            continue
        for part in msg.get("parts", []):
            if part.get("tool_name") == "final_result":
                qs = json.loads(part["args"])
                questions = qs.get("questions", [])
                return questions[0] if questions else None
    return None


def _patch_title(messages: list, title: str) -> None:
    for msg in messages:
        if msg.get("kind") != "response":
            continue
        for part in msg.get("parts", []):
            if part.get("tool_name") == "final_result":
                qs = json.loads(part["args"])
                for q in qs.get("questions", []):
                    q["title"] = title
                part["args"] = json.dumps(qs, ensure_ascii=False)


async def main() -> None:
    index_path = HISTORIES_DIR / "index.json"
    old_index: list[dict] = json.loads(index_path.read_text())
    index_by_file = {e["file"]: e for e in old_index}

    history_files = sorted(f for f in HISTORIES_DIR.glob("*.json") if f.name != "index.json")

    # Load all messages and find questions needing titles
    file_data: list[tuple[Path, list, dict]] = []
    for hf in history_files:
        messages = json.loads(hf.read_text())
        q = _extract_question(messages)
        if q is None:
            print(f"[skip] No question found in {hf.name}")
            continue
        file_data.append((hf, messages, q))

    # Generate titles in parallel
    print(f"Generating titles for {len(file_data)} question(s) using {MODEL}…")
    titles = await asyncio.gather(*[_generate_title(q) for _, _, q in file_data])

    new_index: list[dict] = []

    for (hf, messages, q), title in zip(file_data, titles):
        print(f"  {hf.name}\n    → {title!r}")

        _patch_title(messages, title)

        new_filename = _slug(title) + ".json"
        new_path = HISTORIES_DIR / new_filename

        # Avoid clobbering an unrelated file
        if new_path.exists() and new_path != hf:
            stem = _slug(title, 50)
            new_filename = f"{stem}_{_slug(hf.stem[-8:])}.json"
            new_path = HISTORIES_DIR / new_filename

        new_path.write_text(json.dumps(messages, ensure_ascii=False))
        if new_path != hf:
            hf.unlink()

        entry = index_by_file.get(hf.name, {})
        new_index.append({
            "file": new_filename,
            "exam": entry.get("exam"),
            "topic": title,
        })

    index_path.write_text(json.dumps(new_index, indent=2, ensure_ascii=False))
    print(f"\nDone. index.json updated ({len(new_index)} entries).")


if __name__ == "__main__":
    asyncio.run(main())
