from helpers import get_last_exchanges
from langchain_core.messages import SystemMessage, HumanMessage, AnyMessage
from langchain_openai import ChatOpenAI
from typing import TypedDict

import os
import sys
BASE_DIR = os.getcwd()
sys.path.append(os.path.abspath(os.path.join(BASE_DIR, "..")))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

from prompts.conversation_prompt import CONVERSATION_PROMPT, CONVERSATION_TOOL_PROMPT

class AgentState(TypedDict):
    
    messages: list[AnyMessage]
    domain: dict
    control: dict
    tool_call: dict | None
    tool_result: list | None
    nlu: dict
    escalate: dict


def conversation_node(state: AgentState) -> AgentState:

    llm = ChatOpenAI(
        model="gpt-3.5-turbo",
        temperature=0.2
    )

    route = state["control"].get("route")
    messages = state.get("messages")

    last_exchange = get_last_exchanges(messages, max_exchanges=5)
    last_user_message = next(
        msg.content
        for msg in reversed(state["messages"])
        if isinstance(msg, HumanMessage)
    )
    
    if route == "supported":
        tool_result = state.get("tool_result", [])
    
        messages = [
            SystemMessage(content=CONVERSATION_TOOL_PROMPT.format(
                last_user_message=last_user_message,
                tool_results=str(tool_result)
            ))
        ]
        
    else:
        messages = [
            SystemMessage(content=CONVERSATION_PROMPT.format(history=last_exchange, last_user_message=last_user_message))
        ]
            
    response = llm.invoke(messages)

    return {
        **state,
        "messages": state["messages"] + [response]
    }