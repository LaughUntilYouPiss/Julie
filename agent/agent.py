# imports
import os
import sys
from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.graph import StateGraph, END
from typing import TypedDict

from nodes.classify_intent import classify_intent_node
from nodes.conversation import conversation_node
from nodes.escalate import escalate_node
from nodes.router import router_node
from nodes.small_talk import small_talk_node
from nodes.tools import domain_tool, take_action

from dotenv import load_dotenv
load_dotenv()


# config
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
BASE_DIR = os.getcwd()
sys.path.append(os.path.abspath(os.path.join(BASE_DIR, "..")))

# state
class AgentState(TypedDict):
    
    messages: list[AnyMessage]
    domain: dict
    control: dict
    tool_call: dict | None
    tool_result: list | None
    nlu: dict
    escalate: dict


# agent
class Agent:
    def __init__(self):
        self.graph = self.build_graph()
    
    def build_graph(self):
        graph = StateGraph(AgentState)

        graph.add_node("classify_intent", classify_intent_node)
        graph.add_node("router", router_node)
        graph.add_node("handle_small_talk", small_talk_node)
        graph.add_node("handle_escalate", escalate_node)
        graph.add_node("domain_tool", domain_tool)
        graph.add_node("take_action", take_action)
        graph.add_node("conversation", conversation_node)
                
        graph.add_edge("classify_intent", "router")

        graph.add_conditional_edges(
            "router",
            lambda state: state["control"].get('route'),
            {
                "small_talk": "handle_small_talk",
                "supported": "domain_tool",
                "conversation": "conversation",
                "escalate": "handle_escalate",
            }
        )

        graph.add_edge("domain_tool", "take_action")

        graph.add_conditional_edges(
            "take_action",
            lambda state: state["control"]["status"],
            {
                "entites_manquantes": "conversation",
                "completed": "conversation",
                "failed": "conversation",
                "pending": "router",
                "retry": "router",
            }
        )

        graph.add_edge("handle_small_talk", END)
        graph.add_edge("handle_escalate", END)
        graph.add_edge("conversation", END)

        graph.set_entry_point("classify_intent")

        return graph.compile(debug=True)
    
    def invoke(self, state: AgentState) -> AgentState:
        return self.graph.invoke(state)

if __name__ == "__main__":
    state: AgentState = {
        "messages": [],
        "domain": {},
        "control": {
            "taches": [],
            "executed": [],
            "retry_count": 0,
            "max_retry": 2,
            "current_task": None,
            "failed": None,
            "status": 0,
            "handoff": False
        },
        "tool_call": None,
        "tool_result": [],
        "nlu": {},
        "escalate": {},
    }
    
    agent = Agent()
        
    while True:
        message = str(input("Human: "))
        if message == "quit":
            break

        state["messages"].append(HumanMessage(content=message))

        result = agent.invoke(state)
        if result["messages"]:
            print("Agent: ", result["messages"][-1].content)

        if result["control"].get("handoff"):
            print(" -- Escalation requested. Transfer to human agent.")
            break
        
        state["messages"] = result["messages"]
        state["domain"] = state.get("domain", {"entites": {}})
        state.setdefault("domain", {})
        state["domain"].setdefault("entites", {})

        result_domain = result.get("domain") or {}
        result_entites = result_domain.get("entites") or {}

        for key, value in result_entites.items():
            if value is not None:
                state["domain"]["entites"][key] = value

        state["control"] = result["control"]

        state["tool_call"] = None
        state["tool_result"] = []   
        state["nlu"] = {}
        state["escalate"] = {}

        print(f"DEBUG - CIN actuel: {state['domain']['entites'].get('cin')}")