import os
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from rich.progress import track

from .console import console

load_dotenv()

client = chromadb.PersistentClient(path=os.environ.get('CHROMA_DB_DIR', './chromadb'))

em_fn = OpenAIEmbeddingFunction(
        api_key=os.environ['OPENAI_API_KEY'],
        model_name="text-embedding-3-small"
        )

doc_embed = client.get_or_create_collection(name="docs", embedding_function=em_fn)

class DocumentManager:
    def __init__(self, client=client, embedding_function=em_fn):
        self.name = "documents"
        self.client = client
        self.collection = self.client.get_or_create_collection(name=self.name, embedding_function=embedding_function)
        self.embedding_function = embedding_function

    def add_document(self, path):
        loader = PyPDFLoader(path)
        docs = loader.load()

        for doc in track(docs, description=f"Embedding: {path}"):
            if doc.page_content:
                docid = ":".join([doc.metadata['source'], str(doc.metadata['page'])])
                console.log(f"Adding {docid}")
                self.collection.add(
                        documents = [doc.page_content],
                        metadatas = [doc.metadata],
                        ids = [docid]
                        )

    def add_dir(self, path, pattern=None):
        dir_path = Path(path)

        if pattern:
            file_paths = list(dir_path.glob(pattern))
        else:
            file_paths = list(dir_path.glob("*"))

        console.print(f"Adding: {file_paths}")

        for p in file_paths:
            if not self._in_collection(str(p)):
                self.add_document(p)


    def _in_collection(self, path):
        return path in set([src.split(':')[0] for src in self.collection.get(include=[])['ids']])

    def query(self, text, **kwargs):
        return self.collection.query(query_texts=[text], **kwargs)

    def reset(self, recreate=True):
        self.client.delete_collection(name=self.name)
        if recreate:
            self.collection = self.client.create_collection(name=self.name, embedding_function=self.embedding_function)
