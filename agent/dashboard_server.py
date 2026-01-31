import os
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import mysql.connector
from typing import Optional, Dict, Any

app = FastAPI()

# Mount assets directory to serve CSS and JS
assets_path = os.path.join(os.path.dirname(__file__), "advisor_dashboard", "assets")
app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

# Database config
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "1234",
    "database": "assurances"
}

# State to hold the current handoff
handoff_data = {
    "session_id": "N/A",
    "cin": "N/A",
    "nom": "Inconnu",
    "prenom": "Inconnu",
    "resume": "En attente d'escalade...",
    "derniere_question": "N/A",
    "reason": "N/A",
    "sentiment": "N/A",
    "active": False
}

class EscalationRequest(BaseModel):
    session_id: str
    cin: Optional[str] = "N/A"
    resume: Optional[str] = "N/A"
    derniere_question: Optional[str] = "N/A"
    reason: Optional[str] = "N/A"
    sentiment: Optional[str] = "neutral"

def get_client_details(cin: str):
    if not cin or cin == "N/A" or cin == "null" or cin == "None":
        return "Inconnu", "Inconnu"
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT NOM, PRENOM FROM CLIENT WHERE CIN = %s", (cin,))
        row = cursor.fetchone()
        if row:
            return row[0], row[1]
    except Exception as e:
        print(f"DB Error: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()
    return "Inconnu", "Inconnu"

@app.post("/escalate")
async def trigger_escalation(req: EscalationRequest):
    global handoff_data
    nom, prenom = get_client_details(req.cin)
    print(f"🚨 ESCALADE DÉTECTÉE : Session {req.session_id}, Client {nom} {prenom}")
    handoff_data = {
        "session_id": req.session_id,
        "cin": req.cin,
        "nom": nom,
        "prenom": prenom,
        "resume": req.resume,
        "derniere_question": req.derniere_question,
        "reason": req.reason,
        "sentiment": req.sentiment,
        "active": True
    }
    return {"status": "success"}

@app.get("/handoff-status")
async def get_status():
    return handoff_data

@app.get("/", response_class=FileResponse)
async def dashboard():
    file_path = os.path.join(os.path.dirname(__file__), "advisor_dashboard", "index.html")
    return FileResponse(file_path)

if __name__ == "__main__":
    print("💎 CNP Dashboard Server Starting at http://localhost:8001")
    uvicorn.run(app, host="127.0.0.1", port=8001)
