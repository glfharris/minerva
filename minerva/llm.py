from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from .console import console
from .embed import doc_embed
from .models import Question, Questions

system = """You write single-best answer questions on medical themes. You have the knowledge of a fully-qualified doctor in the UK, therefore use British English, and can speak technically.

        Single-best answer questions consist of:
        * A Stem - text that sets the scene for the lead in, but does not contain a question
        * A Lead in - the actual question that needs answering.
        * 5 possible answers, of which one is correct
        * An explanation

        Please use the following information in your questions, and not from other sources:
        {context}"""

prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system),
                ("human", "Please write 5 dissimilar single-best answer questions on {topic}"),
            ]
        )

llm = ChatOpenAI(model="gpt-4o-mini").with_structured_output(Questions)

generator =  prompt | llm

