import json
from helpers import get_last_exchanges, task_queue
from langchain_core.messages import SystemMessage, HumanMessage, AnyMessage
from langchain_openai import ChatOpenAI
from prompts.classifier_prompt import CLASSIFIER_SYSTEM_PROMPT
from typing import TypedDict

import os
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

import sys
BASE_DIR = os.getcwd()
sys.path.append(os.path.abspath(os.path.join(BASE_DIR, "..")))

class AgentState(TypedDict):
    
    messages: list[AnyMessage]
    domain: dict
    control: dict
    tool_call: dict | None
    tool_result: list | None
    nlu: dict
    escalate: dict

def classify_intent_node(state: AgentState) -> AgentState:
    
    llm_classifier = ChatOpenAI(
        model="gpt-3.5-turbo",
        temperature=0
    )
    
    last_user_message = next(
        msg.content
        for msg in reversed(state["messages"])
        if isinstance(msg, HumanMessage)
    )

    last_interaction = get_last_exchanges(state["messages"], max_exchanges=5)

    messages = [
        SystemMessage(content=CLASSIFIER_SYSTEM_PROMPT),
        SystemMessage(
            content=f"User message:\n{last_user_message}\n\nLes 5 derniers interactions:\n{last_interaction}\n\nReturn ONLY valid JSON."
        )
    ]

    response = llm_classifier.invoke(messages)

    try:
        classification = json.loads(response.content)
    except json.JSONDecodeError:
        classification = {
            "resume_message": "unknown",
            "sentiment": "neutral",
            "entites": {},
            "taches": []
        }

    nlu = state.get("nlu", {})
    domain = state.get("domain", {})
    control = state.get("control", {})
    taches = control.get("taches", [])

    nlu = {
        **nlu,
        "resume_message": classification.get("resume_message", "unknown"),
        "sentiment": classification.get("sentiment", "neutral"),
    }
    entites = domain.get("entites", {}).copy()
    for k, v in classification.get("entites", {}).items():
        if v and str(v).lower() not in ["null", "none"]: 
            entites[k] = v

    domain["entites"] = entites
    
    control = {
        **control,
        "taches":  task_queue(classification.get("taches", []))
    }

    return {
        **state,
        "nlu": nlu,
        "domain": domain,
        "control": control
    }