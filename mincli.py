#! uv run

import typer

from minerva.embed import DocumentManager
from minerva.llm import generator
from minerva.models import Question, Questions

def main(theme: str, save: bool = False, count: int = 1):
    dm = DocumentManager()
    related_docs = dm.query(theme, n_results=50)['documents'][0]
    response = generator.invoke({"topic": theme, "count": str(count), "context": related_docs})

    if type(response) is Question:
        response.show()
    elif type(response) is Questions:
        for q in response.qs:
            q.show()
        if save:
            with open('questions.json', 'w') as f:
                f.write(response.model_dump_json())
    else:
        print(response)


if __name__ == '__main__':
    typer.run(main)
