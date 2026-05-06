#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from minerva.history import make_history_files


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert QuestionSet JSON files into mock few-shot example histories."
    )
    parser.add_argument("files", nargs="+", type=Path, help="QuestionSet JSON files to convert")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("examples/histories"),
        help="Directory for generated history files",
    )
    args = parser.parse_args()

    make_history_files(args.files, args.output)


if __name__ == "__main__":
    main()
