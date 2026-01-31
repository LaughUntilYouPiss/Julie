from langchain_core.messages import SystemMessage, HumanMessage, AnyMessage, AIMessage
from langchain_openai import ChatOpenAI
from typing import TypedDict
import re
import os
import sys
BASE_DIR = os.getcwd()
sys.path.append(os.path.abspath(os.path.join(BASE_DIR, "..")))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

from prompts.small_talk_prompt import SMALL_TALK_PROMPT

class AgentState(TypedDict):
    
    messages: list[AnyMessage]
    domain: dict
    control: dict
    tool_call: dict | None
    tool_result: list | None
    nlu: dict
    escalate: dict




GREETINGS = [
    "bonjour", "bonsoir", "salut", "hello", "coucou", "allô", "allo"
]

FAREWELLS = [
    "au revoir", "aurevoir", "bye", "à bientôt",
    "bonne journée", "bonne soirée", "merci au revoir"
]


def normalize(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text.lower()).strip()


def is_greeting(text: str) -> bool:
    text = normalize(text)
    return any(text == g or text.startswith(g + " ") for g in GREETINGS)


def is_farewell(text: str) -> bool:
    text = normalize(text)
    return any(text == f or text.startswith(f + " ") for f in FAREWELLS)


def greeting_response() -> str:
    return "Bonjour ! Je suis Julie, votre assistante CNP Assurances. Je suis ravie de vous retrouver : que puis-je faire pour vous accompagner aujourd'hui ?"


def farewell_response() -> str:
    return "Merci de votre confiance. Je reste à votre entière disposition pour vos futurs projets. Excellente journée de la part de toute l'équipe CNP Assurances."



def small_talk_node(state: AgentState) -> AgentState:

    last_user_message = next(
        msg.content
        for msg in reversed(state["messages"])
        if isinstance(msg, HumanMessage)
    )
    if is_greeting(last_user_message):
        response_content = state["messages"] + [AIMessage(content=greeting_response())]

    elif is_farewell(last_user_message):
        response_content = state["messages"] + [AIMessage(content=farewell_response())]
    else:
        llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0.7)
        messages = [
            SystemMessage(content=SMALL_TALK_PROMPT),
            HumanMessage(content="Le message utilisateur: \n{last_user_message}")
        ]
        response = llm.invoke(messages)

        response_content = state["messages"] + [
            response
        ]

    return {
        **state, 
        "messages": response_content
    }