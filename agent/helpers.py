from typing import List, Dict, Any, Optional
import heapq
import json
from langchain_core.messages import HumanMessage, AIMessage

import os
import sys
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(BASE_DIR)

from tools.rag_tool import rag_tool
from tools.suivi_sql import search_db_info
#
# from tools.send_communication import send_communication 


INTENT_PRIORITY = {
    "escalate": 0,
    "clarification": 1,
    "faq_av": 2,
    "suivi": 3,
    "hors_perimetre": 4,
    "small_talk": 5
}

INTENT_ALLOWED_TOOLS = {
    "faq_av": {"rag_tool": rag_tool},
    "suivi": {"search_db_info": search_db_info},
    #"commumication": {"send_communication": send_communication}
}

INTENT_REQUIRED_ENTITIES = {
    "suivi": ["cin"]
}

def handle_task_result(control, tool_result: list):
    """
    Updates the task queue state based on the tool result.
    Items in 'taches' are tuples (priority, TaskWrapper).
    """
    # Defensive initialization
    control.setdefault("executed", [])
    control.setdefault("failed", None)
    control.setdefault("retry_count", 0)
    control.setdefault("current_task", None)
    control.setdefault("taches", [])

    taches = control.get("taches", [])

    if tool_result:
        # Task succeeded
        if taches:
            _, wrapper = heapq.heappop(taches)
            control["executed"].append(wrapper.task)
        control["current_task"] = None
        control["retry_count"] = 0
        control["status"] = "completed"
        return control

    # Task failed or no tool result
    control["retry_count"] += 1
    max_retry = control.get("max_retry", 2)

    if control["retry_count"] < max_retry:
        control["status"] = "retry"
        return control

    # Max retries reached
    if taches:
        _, wrapper = heapq.heappop(taches)
        control["failed"] = wrapper.task

    control["current_task"] = None
    control["retry_count"] = 0
    control["status"] = "failed"

    return control

def get_last_exchanges(messages, max_exchanges=5):
    exchanges = []
    current = {}

    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and "agent" not in current:
            current["agent"] = msg.content

        elif isinstance(msg, HumanMessage) and "user" not in current:
            current["user"] = msg.content

        if "user" in current and "agent" in current:
            exchanges.append(current)
            current = {}

        if len(exchanges) >= max_exchanges:
            break

    lines = []
    for ex in exchanges:
        lines.append(f"Utilisateur : {ex['user']}")
        lines.append(f"Agent : {ex['agent']}")

    return "\n".join(lines)

class TaskWrapper:
    def __init__(self, task):
        self.task = task
    def __lt__(self, other):
        return False  # Never compare tasks, rely on priority only

def task_queue(tasks):
    queue = []
    for task in tasks:
        intent = task.get("intent", "unknown")
        priority = INTENT_PRIORITY.get(intent, 999)
        #heapq.heappush(queue, (priority, task))
        heapq.heappush(queue, (priority, TaskWrapper(task)))
    return queue

def dequeue_next_task(queue):
    if not queue:
        return None
    _, wrapper = heapq.heappop(queue)
    return wrapper.task



def extract_tool_call(response):
        # Cas 1 : tool_calls structuré
        tool_calls = response.tool_calls
        if tool_calls:
            return tool_calls
        # Cas 2 : tool_uses dans le content
        try:
            content = response.content.strip()
    
            # Certains modèles répètent le JSON → on prend le premier bloc
            if content.startswith("{"):
                json_block = content.split("\n}\n")[0] + "\n}"
                data = json.loads(json_block)
    
                tool_uses = data.get("tool_uses")
                if tool_uses:
                    # Normalisation vers un format unique
                    return [{
                        "name": tool_uses[0]["recipient_name"].replace("functions.", ""),
                        "args": tool_uses[0]["parameters"]
                    }]
        except Exception:
            pass
    
        return None