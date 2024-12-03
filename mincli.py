#! uv --env-file .env run

import typer

from minerva.embed import DocumentManager
from minerva.llm import generator
from minerva.models import Question

def main(theme: str):
    dm = DocumentManager()
    related_docs = dm.query(theme)['documents'][0]
    response = generator.invoke({"topic": theme, "context": related_docs})

    if type(response) is Question:
        response.show()
    elif type(response) is List[Question]:
        for q in response:
            q.show()
    else:
        print(response)


if __name__ == '__main__':
    typer.run(main)
