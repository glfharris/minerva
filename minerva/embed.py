import os
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
from langchain_community.document_loaders import PyPDFLoader
from rich.progress import track

from .console import console

class EmbedClient:
    def __init__(self, api_key=os.environ['OPENAI_API_KEY'],
                 chroma_db_dir=os.environ['CHROMA_DB_DIR'],
                 embedding_model="text-embedding-3-small"):
        self.chroma_client = chromadb.PersistentClient(path=chroma_db_dir)

        self.embedding_function = OpenAIEmbeddingFunction(
        api_key=api_key,
        model_name=embedding_model
        )

        self.documents = DocumentManager(client=self.chroma_client,
                               embedding_function=self.embedding_function)

    def reset(self):
        self.documents.reset()


class DocumentManager:
    def __init__(self, client=client, embedding_function=em_fn):
        self.name = "documents"
        self.client = client
        self.collection = self.client.get_or_create_collection(name=self.name, embedding_function=embedding_function)
        self.embedding_function = embedding_function

    def add(self, path):
        loader = PyPDFLoader(path)
        docs = loader.load()

        documents = [doc.page_content for doc in docs if doc.page_content]
        metadatas = [doc.metadata for doc in docs if doc.page_content]
        ids = [":".join([doc.metadata['source'],str(doc.metadata['page'])]) for doc in docs if doc.page_content]

        self.collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids)

    def add_dir(self, path, pattern=None):
        dir_path = Path(path)

        if pattern:
            file_paths = list(dir_path.glob(pattern))
        else:
            file_paths = list(dir_path.glob("*"))

        console.log(f"Found {len(file_paths)} file(s) - {[str(p) for p in file_paths]}")

        for i, p in enumerate(file_paths):
            if not self._in_collection(str(p)):
                with console.status(f"Embedding {p}"):
                    self.add(p)
                console.log(f"Embedded {p} - {i + 1}/{len(file_paths)}")


    def _in_collection(self, path):
        return path in set([src.split(':')[0] for src in self.collection.get(include=[])['ids']])

    def query(self, text, **kwargs):
        return self.collection.query(query_texts=[text], **kwargs)

    def reset(self, recreate=True):
        self.client.delete_collection(name=self.name)
        if recreate:
            self.collection = self.client.create_collection(name=self.name, embedding_function=self.embedding_function)
