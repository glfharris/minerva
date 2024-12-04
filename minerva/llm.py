from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from .console import console
from .embed import doc_embed
from .models import Question, Questions

system = """You write single-best answer questions for the Royal College of Anaesthetist's
        Primary FRCA examinations. Therefore questions should be in British English, and set
        at an appropriate standard for doctors with some experience working in anaesthesia.

        Single-best answer questions consist of:
        * A Stem - text that sets the scene for the lead in, but does not contain a question
        * A Lead in - the actual question that needs answering.
        * 5 possible answers, of which one is correct
        * An explanation

        Please use the following information in your questions, and not from other sources:
        {context}

        These are some examples of single best answer questions:
        {examples}"""

prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system),
                ("human", "Please write {count} dissimilar single-best answer question(s) on {topic}"),
            ]
        )

llm = ChatOpenAI(model="gpt-4o").with_structured_output(Questions)

generator =  prompt | llm

