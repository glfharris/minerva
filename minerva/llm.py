from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from .console import console
from .embed import EmbedClient
from .models import Question, Questions

role = """You write single-best answer questions for the Royal College of 
        Anaesthetist's Primary FRCA examinations. Therefore questions should be
        in British English, and set at an appropriate standard for doctors with
        some experience working in anaesthesia. When using patient examples
        there should be a variety of ages and geneders, appropriate for the
        context of the question.

        Single-best answer questions consist of:
        * A Stem - text that sets the scene for the lead in, but does not
            contain a question
        * A Lead in - the actual question that needs answering.
        * 5 possible answers, of which one is correct
        * An explanation\n"""

class LLMClient:
    def __init__(self, api_key, chroma_db_dir,
                 embedding_model, question_model, temperature):
        self.api_key = api_key
        self.chroma_db_dir = chroma_db_dir
        self.embedding_model = embedding_model
        self.question_model = question_model
        self.embed = EmbedClient(api_key=self.api_key,
                                 chroma_db_dir=self.chroma_db_dir,
                                 embedding_model=self.embedding_model)
        self.llm = ChatOpenAI(model=self.question_model,
                              temperature=temperature).with_structured_output(Questions)
        self.prompt_messages = [("system", role)]

    def generate(self,topic, count, examples=None):

        documents = self.embed.documents.query(topic)

        if documents:
            self.prompt_messages.append(("system",
                """Please use the following information in your creation:
                {documents}"""))
        if examples:
            self.prompt_messages.append(("system",
                """Here are some examples of Single-Best Answer Questions:
                {examples}"""))

        self.prompt_messages.append(("user",
                "Please write {count} dissimilar single best answer questions on {topic}"))

        prompt = ChatPromptTemplate.from_messages(self.prompt_messages)

        self.chain = prompt | self.llm

        return self.chain.invoke({"topic": topic, "count": count,
                                  "documents": documents, "examples": examples})


