from langchain_core.messages import SystemMessage, HumanMessage, AnyMessage
from langchain_openai import ChatOpenAI
from typing import TypedDict

import os
import sys
BASE_DIR = os.getcwd()
sys.path.append(os.path.abspath(os.path.join(BASE_DIR, "..")))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

from prompts.escalate_prompt import ESCALATE_PROMPT, TRANSFER_PROMPT

class AgentState(TypedDict):
    
    messages: list[AnyMessage]
    domain: dict
    control: dict
    tool_call: dict | None
    tool_result: list | None
    nlu: dict
    escalate: dict


def escalate_node(state: AgentState) -> AgentState:

    control = state.get("control", {})
    escalate = state.get("escalate", {})
    
    last_user_message = next(
        msg.content
        for msg in reversed(state["messages"])
        if isinstance(msg, HumanMessage)
    )

    llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0.3)

    messages = [
        SystemMessage(content=ESCALATE_PROMPT),
        HumanMessage(content="Le message de l'utilisateur: {last_user_message}")
    ]
    response = llm.invoke(messages)
    updated_messages = state["messages"] + [
        response
    ]
    
    interaction = "\n".join(
        f"{msg.type.upper()}: {msg.content}"
        for msg in state["messages"]
    )

    messages = [
        SystemMessage(content=TRANSFER_PROMPT.format(messages=interaction))
    ]
    resume = llm.invoke(messages)
    resume = resume.content
    info_utilisateur = state.get('domain')
    sentiment = state.get('nlu')['sentiment']
    
    
    return {
        **state,
        "messages": updated_messages,
        "control": {
            **control,
            "handoff": True
        },
        "escalate": {
            **escalate,
            "sentiment": sentiment,
            "derniere_question": last_user_message,
            "resume_interaction": resume,
            "info_utilisateur": info_utilisateur
        }
    }