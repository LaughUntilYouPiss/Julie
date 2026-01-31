from langchain_core.messages import AnyMessage
from typing import TypedDict


class AgentState(TypedDict):
    messages: list[AnyMessage]
    domain: dict
    control: dict
    tool_call: dict | None
    tool_result: list | None
    nlu: dict
    escalate: dict


def router_node(state: AgentState) -> AgentState:

    raison = None
    route = None

    control = state.get("control", {})
    taches = control.get("taches", [])
    current_task = control.get("current_task")
    tool_result = state.get("tool_result", None)
    
    if current_task is None and taches:
        _, tache = taches[0]
        control["current_task"] = tache
        current_task = tache#.task
        control["retry_count"] = 0

    current_task = current_task.task
    intent = current_task.get("intent", "inconnu") if current_task else "inconnu"
    confidence = current_task.get("confidence", 0.0) if current_task else 0.0
    # print(f"Routing decision for intent='{intent}' with confidence={confidence}")
    
    if intent == "small_talk":
        route = "small_talk"
        control["current_task"] = None

    elif confidence <= 0.4: # clarification
        raison = "Demande ambiguë"
        route = "escalate"
        control["current_task"] = None

    elif intent == "escalate":
        raison = "Demande necessite intervention humaine"
        route = "escalate"
        control["current_task"] = None

    elif intent == "hors_perimetre":
        raison = "Demande non prise en charge par le bot"
        route = "escalate"
        control["current_task"] = None

    elif intent == "clarification":
        route = "conversation"
        control["current_task"] = None
        
    else:
        route = "supported"
        
        if control["failed"] is not None:
            raison = "Échec technique lors du traitement de la demande"
            route = "escalate"

    return {
        **state,
        "control": {
            **control,
            "route": route,
        },
        "tool_result": tool_result,
        "escalate": {
            "raison_transfert": raison
        } if route == "escalate" else {}
    }