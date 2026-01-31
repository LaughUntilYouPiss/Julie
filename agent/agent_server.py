import os
import sys
import json
import re
import requests


import mysql.connector
from dotenv import load_dotenv
from typing import TypedDict, Annotated, Optional, Dict, Any, List
import operator
# Imports LangChain / LangGraph
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, ToolMessage, AIMessage
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from agent import Agent, AgentState


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
    
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "1234", # Updated based on typical local setups or notebook defaults, check notebook
    "database": "assurances"
}
# Note: Notebook had password "1234", let's use that.
# --- WHISPER & AUDIO CONFIG ---


def db_save_message(session_id: str, direction: str, content: str, cin: Optional[str] = None):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Check session
        cursor.execute("SELECT ID_SESSION FROM SESSION_CALLBOT WHERE ID_SESSION = %s", (session_id,))
        if not cursor.fetchone():
            # For simplicity, we create a session if it doesn't exist
            client_id = None
            if cin:
                cursor.execute("SELECT ID_CLIENT FROM CLIENT WHERE CIN = %s", (cin,))
                res = cursor.fetchone()
                if res: client_id = res[0]
            cursor.execute("INSERT INTO SESSION_CALLBOT (ID_SESSION, ID_CLIENT) VALUES (%s, %s)", (session_id, client_id))
            
        # Get client_id if not session creation time
        client_id = None
        if cin:
            cursor.execute("SELECT ID_CLIENT FROM CLIENT WHERE CIN = %s", (cin,))
            res = cursor.fetchone()
            if res: client_id = res[0]

        query = """
            INSERT INTO MESSAGE (ID_SESSION, ID_CLIENT, DIRECTION, CONTENU, DATE_ENVOI, CANAL, STATUT_MESSAGE)
            VALUES (%s, %s, %s, %s, NOW(), 'VOICE', 'SENT')
        """
        cursor.execute(query, (session_id, client_id, direction, content))
        conn.commit()
    except Exception as e:
        print(f"❌ DB Persistence Error: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()
            
def db_save_escalation(session_id: str, reason: str):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT ID_CONSEILLER FROM CONSEILLER LIMIT 1")
        advisor = cursor.fetchone()
        advisor_id = advisor[0] if advisor else 1

        query = "INSERT IGNORE INTO ESCALATE (ID_SESSION, ID_CONSEILLER, RAISON) VALUES (%s, %s, %s)"
        cursor.execute(query, (session_id, advisor_id, reason))
        conn.commit()
    except Exception as e:
        print(f"❌ DB Escalation Error: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()
            



app = Agent()
server = FastAPI()

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    intent: Optional[str] = None
    extracted_data: Optional[Dict[str, Any]] = None

# Simple in-memory session store
sessions: Dict[str, Any] = {}

@server.post("/chat")
async def chat_endpoint(req: ChatRequest):
    print(f"📩 Received: {req.message} (Session: {req.session_id})")
    
    # Init session if needed
    if req.session_id not in sessions:
        sessions[req.session_id] = {
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
    
    current_state = sessions[req.session_id]


        
    # --- COHERENCE: Ingest Bridge Data (CIN, Dossier, Intent) ---
    if req.extracted_data:
        current_state.setdefault("domain", {})
        current_state["domain"].setdefault("entites", {})

        cin_bridge = req.extracted_data.get("cin")
        cin_bridge = re.sub(r'[^a-zA-Z0-9]', '', cin_bridge).lower()
        if cin_bridge and str(cin_bridge).lower() not in ["null", "none"]:  # IMPORTANT: only overwrite if non-null and valid
            print(f"🔑 CIN received from Bridge: {cin_bridge}")
            current_state["domain"]["entites"]["cin"] = cin_bridge


    # Ingest Dossier
    # Accept either 'dossier' or 'dossier_id' from bridge

   #dossier_bridge = req.extracted_data.get("dossier") or req.extracted_data.get("dossier_id")
    #if dossier_bridge:
    #    print(f"📂 Dossier received from Bridge: {dossier_bridge}")
    #    current_state["domain"]["entites"]["dossier_id"] = dossier_bridge


    #if req.intent:
     #   if "nlu" not in current_state: current_state["nlu"] = {}
      #  print(f"🧠 Intent received from Bridge: {req.intent}")
        # current_state["nlu"]["intent"] = req.intent
    # -------------------------------------------------------------
    
    current_state["messages"].append(HumanMessage(content=req.message))
    
    # Save user message to DB
    cin = current_state.get("domain", {}).get("entites", {}).get("cin")
    db_save_message(req.session_id, "USER", req.message, cin)

    # Reset transient control flags for new turn
    #control = current_state.setdefault("control", {})
    #control.setdefault("taches", [])
    #control.setdefault("executed", [])
    #control.setdefault("failed", None)
    #control.setdefault("retry_count", 0)
    #control.setdefault("max_retry", 2)
    #control.setdefault("current_task", None)
    #control.setdefault("status", 0)
    #control.setdefault("handoff", False)

    # Run Agent
    try:
        final_state = app.invoke(current_state)
        sessions[req.session_id] = final_state 
        
        # Extract response
        response_text = "Je n'ai pas de réponse."
        if final_state["messages"] and isinstance(final_state["messages"][-1], AIMessage):
            response_text = final_state["messages"][-1].content
        
        # Save bot message to DB
        db_save_message(req.session_id, "BOT", response_text, cin)

        # Handle Escalation save
        #intent = final_state.get("intent") or final_state.get("control", {}).get("intent")
        #if intent == "escalate":
        #    db_save_escalation(req.session_id, "Demande de contact humain détectée.")

        # Update state with results (persistence)
        current_state["messages"] = final_state["messages"]
        
        final_domain = final_state.get("domain", {})
        final_entites = final_domain.get("entites", {})
        for k, v in final_entites.items():
            if v:
                current_state["domain"]["entites"][k] = v

        current_state.setdefault("control", {})
        current_state["control"]["entites_manquantes"] = None

        # Trigger Dashboard Escalation if handoff is detected
        if final_state.get("control", {}).get("handoff"):
            print("🚨 Handoff detected! Updating Dashboard...")
            try:
                # Map internal keys to dashboard keys
                escalation_payload = {
                    "session_id": req.session_id,
                    "cin": final_state.get("domain", {}).get("entites", {}).get("cin"),
                    "resume": final_state.get("escalate", {}).get("resume_interaction", "Aucun résumé disponible."),
                    "derniere_question": final_state.get("escalate", {}).get("derniere_question", req.message),
                    "reason": final_state.get("escalate", {}).get("raison_transfert", "Demande de contact humain."),
                    "sentiment": final_state.get("escalate", {}).get("sentiment", "N/A")
                }
                requests.post("http://localhost:8001/escalate", json=escalation_payload, timeout=2)
            except Exception as e:
                print(f"⚠️ Error contacting Dashboard Server: {e}")

        print(f"📤 Sending: {response_text}")
        return {"response": response_text}
        
    except Exception as e:
        import traceback
        traceback.print_exc() # Print full stack trace to server console
        print(f"❌ Error: {e}")
        return {"response": f"Désolé, erreur serveur : {str(e)}"}

if __name__ == "__main__":
    print("🚀 Starting Agent Server on port 8000...")
    uvicorn.run(server, host="0.0.0.0", port=8000)