from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from minerva.history import make_history_files


def make_history(
    files: Annotated[list[Path], typer.Argument(help="QuestionSet JSON files to convert")],
    output: Annotated[Path, typer.Option("-o", "--output")] = Path("examples/histories"),
) -> None:
    """Convert QuestionSet JSON files into mock few-shot example histories."""
    make_history_files(files, output)
