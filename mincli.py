#! uv run
from __future__ import annotations

from minerva.cli.app import app
from minerva.console import console


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
