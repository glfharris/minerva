#! uv run
from pathlib import Path
from typing import Optional
from typing_extensions import Annotated

from dotenv import load_dotenv
import typer

from minerva.console import console
from minerva.embed import EmbedClient
from minerva.llm import LLMClient

load_dotenv()

app = typer.Typer()
context = {
        "API_KEY": None,
        "CHROMA_DB_DIR": None,
        "EMBEDDING_MODEL": "text-embedding-3-small",
        "QUESTION_MODEL": "gpt-4o"
        }

@app.callback()
def main(openai_api_key: Annotated[str,
                typer.Option(envvar="OPENAI_API_KEY")] = "",
         chroma_db_dir: Annotated[Path,
                typer.Option(envvar="CHROMA_DB_DIR")] = Path("./chromadb")
         ):
    if not openai_api_key:
        print("$OPENAI_API_KEY not set")
        typer.Exit(1)
    else:
        context['API_KEY'] = openai_api_key

    context['CHROMA_DB_DIR'] = str(chroma_db_dir)


@app.command()
def create(topic: Annotated[str, 
                typer.Argument(help="Question topic")],
           count: Annotated[int,
                typer.Option("-c", "--count",
                             help="Number of questions to generate")] = 1,
           temperature: Annotated[float,
                typer.Option("-t", "--temperature",
                             help="Temperature of the LLM")] = 0.7
           ):
    minerva_client = LLMClient(api_key=context['API_KEY'],
                               chroma_db_dir=context['CHROMA_DB_DIR'],
                               embedding_model=context['EMBEDDING_MODEL'],
                               question_model=context['QUESTION_MODEL'],
                               temperature=temperature)
    with open('examples/rcoa.md', 'r') as f:
        examples = f.read()
    with console.status(f"Creating {count} question(s) on {topic}"):
        results = minerva_client.generate(topic,count,examples=examples.split('---'))
    for q in results.qs:
        q.show()

@app.command()
def embed(path: Annotated[Optional[Path],
            typer.Argument(help="Path of document(s) to embed")] = None,
        reset: Annotated[bool, 
            typer.Option(help="Resets existing embeddings")] = False):

    embed = EmbedClient(api_key=context['API_KEY'],
                        chroma_db_dir=context['CHROMA_DB_DIR'],
                        embedding_model=context['EMBEDDING_MODEL'])
    if reset:
        console.log("Resetting embeddings")
        embed.reset()

    if path:
        if path.is_dir():
            embed.documents.add_dir(path)
        elif path.is_file():
            embed.documents.add_document(path)
        else:
            console.log(f"Unable to process {path}. Quitting")
            typer.Exit(1)

if __name__ == '__main__':
    app()
