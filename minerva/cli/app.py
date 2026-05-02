from __future__ import annotations

import logging
import os
import warnings

import typer
from dotenv import load_dotenv

os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("transformers").setLevel(logging.WARNING)
logging.getLogger("statsmodels").setLevel(logging.WARNING)
warnings.filterwarnings("ignore", module="statsmodels")

load_dotenv()

from minerva.cli.commands.convert import convert
from minerva.cli.commands.create import create
from minerva.cli.commands.critique import critique
from minerva.cli.commands.embed import embed
from minerva.cli.commands.history import make_history
from minerva.cli.commands.match import match
from minerva.cli.commands.quiz import quiz
from minerva.cli.commands.validate import validate

app = typer.Typer(no_args_is_help=True)

app.command()(match)
app.command()(create)
app.command()(embed)
app.command()(quiz)
app.command()(critique)
app.command()(convert)
app.command("make-history")(make_history)
app.command()(validate)
