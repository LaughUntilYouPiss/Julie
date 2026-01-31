from helpers import (
    INTENT_REQUIRED_ENTITIES,
    INTENT_ALLOWED_TOOLS,
    extract_tool_call,
    handle_task_result
)

from langchain_core.messages import SystemMessage, HumanMessage, AnyMessage
from langchain_openai import ChatOpenAI
from typing import TypedDict
import os
import sys

BASE_DIR = os.getcwd()
sys.path.append(os.path.abspath(os.path.join(BASE_DIR, "..")))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

from prompts.tools_prompt import TOOLS_PROMPT


# ======================================================
# STATE
# ======================================================

class AgentState(TypedDict):
    messages: list[AnyMessage]
    domain: dict
    control: dict
    tool_call: dict | None
    tool_result: list | None
    nlu: dict
    escalate: dict


# ======================================================
# DOMAIN TOOL SELECTION
# ======================================================

def domain_tool(state: AgentState) -> AgentState:
    
    current_task = state["control"]["current_task"].task
    intent = current_task.get("intent")
    entities = state["domain"].get("entites", {})
    control = state.get("control", {})
    # current_task = control.get("current_task", {}).task

    required_entities = INTENT_REQUIRED_ENTITIES.get(intent, [])
    missing = []
    missing = [
        e for e in required_entities
        if e not in entities or entities[e] in (None, "", [])
    ]

    print(f"Required entities for intent '{intent}': {required_entities}, missing: {missing}")

    if missing:
        tool_result = state.get("tool_result", [])        
        tool_result.append(f"Entite manquante: {missing}")
        return {
            **state,
            "control": {
                **control,
                "status": "entites_manquantes",
            },
            "tool_result": tool_result
        }

    # Récupère le dernier message utilisateur
    last_user_message = next(
        msg.content
        for msg in reversed(state["messages"])
        if isinstance(msg, HumanMessage)
    )

    # Bind ONLY tools allowed for this intent
    allowed_tool_names = list(INTENT_ALLOWED_TOOLS[intent].keys())
    allowed_tools = list(INTENT_ALLOWED_TOOLS[intent].values())
    print(f"Allowed tool names for intent '{intent}': {allowed_tool_names}")
    print(f"Allowed tools for intent '{intent}': {allowed_tools}")
    
    # LLM pour sélectionner l'outil
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0  # Décision stable
    ).bind_tools(allowed_tools)  # tools = dictionnaire de fonctions

    # Prompt système adapté aux tools
    messages = [
        SystemMessage(content=TOOLS_PROMPT.format(cin=entities.get("cin"))),
        HumanMessage(content=f"""
Objectif :
{current_task['description']}
Contexte utilisateur :
{last_user_message}
Règle : un seul appel d’outil.
"""
        )
    ]

    # Appel LLM
    response = llm.invoke(messages)
    print(response)
    # Récupération du tool sélectionné par le LLM
    tool_calls = extract_tool_call(response)
    print(f"Extracted tool calls: {tool_calls}, {len(tool_calls) if tool_calls else 0}")
    if not tool_calls or len(tool_calls) != 1:
        return {
            **state,
            "control": {
                **control,
                "status": "tool_selection_failed",
            },
        }
        
    tool_call = tool_calls[0]
    tool_name = tool_call["name"]
    
    if tool_name not in allowed_tool_names:
        return {
            **state,
            "control": {
                **control,
                "status": "tool_selection_failed",
            },
        }

    # Valid outcome: tool selected
    return {
        **state,
        "tool_call": tool_call,
        "control": {
                **control,
                "status": "tool_selected",
            },
    }


# ======================================================
# TOOL EXECUTION
# ======================================================

def take_action(state: AgentState):

    intent_allowed_tools = INTENT_ALLOWED_TOOLS
    control = state.get("control", {})

    if control["status"] == "entites_manquantes":
        return state

    if control["status"] != "tool_selected":
        control = handle_task_result(control, [])
        return {
            **state,
            "control": control,
        }
    
    task = control.get("current_task")
    task = task.task
    if not task:
        return state
    
    intent = task.get("intent", "inconnu")
    tool_call = state.get("tool_call", {})
    tool_name = tool_call.get("name")
    tool_args = tool_call.get("args", {})
        
    allowed_tools_for_intent = intent_allowed_tools[intent]
    tool_fn = allowed_tools_for_intent[tool_name]
        
    try: 
        result = tool_fn.invoke(tool_args)
        
    except Exception as e:
        control["retry_count"] += 1
        control["status"] = "retry"
        return {
            **state,
            "control": control,
            "tool_error": str(e)
        }
    
    tool_result = state.get("tool_result", [])
    tool_result.append({
        "tool": tool_name,
        "input": tool_args,
        "output": result
    })

    control = handle_task_result(control, tool_result)

    if control["taches"] != []:
        control["status"] = "pending"
    else:
        control["status"] = "completed"
    
    return {
        **state,
        "control": control,
        "tool_result": tool_result
    }