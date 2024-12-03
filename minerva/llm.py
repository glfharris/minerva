from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from .console import console
from .embed import doc_embed
from .models import Question, Choice

system = """You write single-best answer questions on medical themes. You have the knowledge of a fully-qualified doctor in the UK, therefore \
        use British English, and can speak technically.

        Single-best answer questions have a stem, a lead-in question, 5 possible answers, of which 1 is correct, and an explanation.

        Please use the following information in your creations:
        {context}"""

prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system),
                ("human", "Please write a single-best answer question on {topic}"),
            ]
        )

llm = ChatOpenAI(model="gpt-4o-mini").with_structured_output(Question)

generator =  prompt | llm

