# =========================
# IMPORTS
# =========================
import eel
import threading
import time
import sounddevice as sd
import numpy as np
import wavio
import tempfile
import whisper
import requests
import os
import json
import datetime
import random
import sys
from openai import OpenAI
from dotenv import load_dotenv

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from typing import TypedDict, Union, List, Dict, Any, Optional

# Ajout du parent au path pour importer les tools
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

class AgentState(TypedDict):
    messages: list[Union[HumanMessage, AIMessage, ToolMessage, SystemMessage]]
    domain: Optional[dict]
    control: Optional[dict]

# =========================
# CONFIG & ENV
# =========================
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
tts_client = OpenAI(api_key=API_KEY) if API_KEY else None
SERVER_URL = "http://127.0.0.1:8000/chat"
SILENCE_THRESHOLD = 0.01

# =========================
# PROMPT LLM FINAL (LOGIQUE CORRIGÉE)
# =========================
LLM_GUARD_PROMPT = """
Tu es un LLM de garde pour un callbot d’assurance.
Tu reçois des phrases transcrites par Whisper (speech-to-text).

TON RÔLE :

1. FILTRER LA LANGUE
- Si la phrase n’est PAS en français (anglais, arabe, espagnol, bruit, phrase mixte non compréhensible), BLOQUE-LA.
- Si la phrase est en FRANÇAIS, même très courte (ex : "Bonjour", "Oui", "Non"), LAISSE PASSER.

2. ANALYSE DE LA PHRASE
- Nettoie la transcription :
  - supprime les répétitions,
  - supprime les hésitations (euh, hum, ah),
  - corrige légèrement la formulation si nécessaire sans changer le sens.
- Reformule la phrase de manière propre et claire.
- Extrais les entités si présentes :
  - CIN (ex : JB200904, AB123456)
  - Numéro de dossier (ex : AAV-2026-1234)
- Détecte l’intention métier si possible, sinon mets null.

INTENTIONS MÉTIER POSSIBLES (exemples) :
- prise_en_charge_credit_immobilier
- declaration_sinistre
- suivi_dossier
- remboursement
- informations_contrat
- resiliation
- autre

RÈGLES DE DÉCISION (ACTION) :
- SI (Français ET intelligible) → action = "send_to_server"
- SI (Non français OU incompréhensible) → action = "ask_client"

IMPORTANT :
- Ne bloque JAMAIS une phrase française, même courte ou incomplète.
- Toute phrase française doit être envoyée au serveur.
- Pour action = "ask_client", le contenu DOIT être exactement :
  "Je ne comprends que le français, pouvez-vous répéter ?"

FORMAT DE SORTIE — JSON STRICT UNIQUEMENT :
{
  "content": "Reformulation propre de la phrase",
  "has_intent": true | false,
  "intent": "type_d_intention_ou_null",
  "extracted_data": {
    "cin": "XXXX | null",
    "dossier": "XXXX | null"
  },
  "action": "send_to_server" | "ask_client"
}

"""
#########################################################################
SUMMARY_PROMPT = """Tu es un assistant rédactionnel professionnel qui se présente au nom de CNP Assurances.

OBJECTIF
À partir :
- du nom et prénom du client fournis en entrée
- d'un historique de conversation structuré sous forme de liste contenant des HumanMessage et AIMessage (format LangGraph)

Tu dois reformuler l'ensemble des échanges en un email professionnel en français, prêt à être envoyé, comprenant un Subject (Objet) et un Body.

ENTRÉES
- Nom du client : {prenom_client} {nom_client}
- Historique : liste chronologique de HumanMessage et AIMessage

POSTURE ET RÈGLES
- Tu écris exclusivement en tant que CNP Assurances
- Ton est formel standard, professionnel et clair
- Tu n'inventes aucune information
- Tu utilises uniquement les informations explicitement présentes dans l'historique
- Tu ne mentionnes jamais l'existence d'un historique, de messages, d'IA ou de LangGraph

FORMAT DE SORTIE OBLIGATOIRE

1) SUBJECT (OBJET)
- Clair, concis et professionnel
- Représente le sujet principal du dossier tel qu'identifié dans l'historique

2) BODY DE L'EMAIL
Le body doit être structuré en sections distinctes.
Chaque section ne doit apparaître que si l'information correspondante est présente dans l'historique.

SECTIONS DU BODY

INTRODUCTION (TOUJOURS PRÉSENTE)
- Salutation personnalisée :
  « Madame / Monsieur {prenom_client} {nom_client}, »
- Phrase indiquant que l'email fait suite aux échanges avec CNP Assurances.

STATUT DU DOSSIER
- À inclure uniquement si un statut du dossier est mentionné ou clairement identifiable dans l'historique
- Ne jamais deviner ni créer un statut

DOCUMENTS À REMETTRE
- À inclure uniquement si des documents sont demandés ou évoqués dans l'historique
- Présenter la liste de manière claire
- Ne jamais ajouter de documents non mentionnés

INFORMATIONS IMPORTANTES / DÉFINITIONS
- À inclure uniquement si l'historique contient des explications, définitions ou précisions contractuelles ou réglementaires
- Reformuler ces éléments de manière claire et professionnelle

CONCLUSION (TOUJOURS PRÉSENTE)
- Phrase de clôture professionnelle indiquant la disponibilité de CNP Assurances

SIGNATURE (TOUJOURS PRÉSENTE)
Cordialement,

CNP Assurances
Service Clients

CONTRAINTES STRICTES
- Ne jamais créer de section vide
- Ne jamais ajouter d'informations absentes de l'historique
- Produire un email fluide, structuré et professionnel
- Retourne UNIQUEMENT un JSON avec les clés "subject" et "body"
"""

def get_client_name_by_cin(cin: str):
    """Récupère le prénom et nom du client via son CIN."""
    try:
        from tools.send_communication import get_client_info_by_cin
        info = get_client_info_by_cin(cin)
        if info:
            return info.get("PRENOM"), info.get("NOM")
    except Exception:
        pass
    return None

def reformulate_history_to_email(state: AgentState, cin: str) -> Dict[str, str]:
    """
    Reformule l'historique de conversation en un email professionnel.
    
    Args:
        state: L'état de l'agent contenant les messages
        cin: Le CIN du client pour récupérer ses informations
    
    Returns:
        Dict avec 'subject' et 'body' de l'email reformulé
    """
    # Récupération des informations du client depuis la base de données
    try:
        
        client_info = get_client_name_by_cin(cin)
        if client_info:
            prenom_client , nom_client= client_info
        else:
            prenom_client = "Client"
            nom_client = ""
    except Exception:
        # Fallback si la récupération échoue
        prenom_client = "Client"
        nom_client = ""
    
    # Récupération de l'historique des messages
    messages = state.get("messages", [])
    
    # Formatage de l'historique pour le prompt
    history_text = ""
    for msg in messages:
        if isinstance(msg, HumanMessage):
            history_text += f"HumanMessage: {msg.content}\n"
        elif isinstance(msg, AIMessage):
            history_text += f"AIMessage: {msg.content}\n"
        elif isinstance(msg, ToolMessage):
            history_text += f"ToolMessage: {msg.content}\n"
    
    # Préparation du prompt
    llm_json = ChatOpenAI(
        model="gpt-3.5-turbo", 
        temperature=0,
        model_kwargs={"response_format": {"type": "json_object"}}
    )
    
    prompt_filled = SUMMARY_PROMPT.format(
        prenom_client=prenom_client,
        nom_client=nom_client
    )
    
    input_messages = [
        SystemMessage(content=prompt_filled),
        HumanMessage(content=f"Historique de conversation:\n{history_text}\n\nReformule cet historique en email professionnel.")
    ]
    
    # Appel au LLM
    response = llm_json.invoke(input_messages)
    email_data = json.loads(response.content.strip())
    
    return {
        "subject": email_data.get("subject", "Suivi de votre dossier"),
        "body": email_data.get("body", "")
    }
# =========================
# LLM DECISION
# =========================
import json
import re

def llm_guard_decision(text: str) -> dict:
    try:
        response = tts_client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[
                {"role": "system", "content": LLM_GUARD_PROMPT},
                {"role": "user", "content": text}
            ]
        )

        raw_output = response.choices[0].message.content.strip()

        # Tentative d’extraction du JSON même s’il y a du texte autour
        match = re.search(r"\{[\s\S]*\}", raw_output)
        if match:
            try:
                decision = json.loads(match.group())
            except json.JSONDecodeError:
                decision = None
        else:
            decision = None

        # Si aucun JSON valide → on laisse passer la phrase
        if not isinstance(decision, dict):
            return {
                "content": text,
                "has_intent": False,
                "intent": None,
                "extracted_data": {"cin": None, "dossier": None},
                "action": "send_to_server"
            }

        # Sécurisation des champs attendus
        decision.setdefault("content", text)
        decision.setdefault("has_intent", False)
        decision.setdefault("intent", None)
        decision.setdefault("extracted_data", {"cin": None, "dossier": None})
        decision.setdefault("action", "send_to_server")

        # Normalisation CIN
        cin = decision.get("extracted_data", {}).get("cin")
        if cin:
            cin = re.sub(r'[^a-zA-Z0-9]', '', cin).lower()
            decision["extracted_data"]["cin"] = cin.strip()

        # Sécurité finale sur action
        if decision["action"] not in ("send_to_server", "ask_client"):
            decision["action"] = "send_to_server"

        return decision

    except Exception:
        # Exception technique → ne jamais bloquer l’utilisateur
        return {
            "content": text,
            "has_intent": False,
            "intent": None,
            "extracted_data": {"cin": None, "dossier": None},
            "action": "send_to_server"
        }


# =========================
# AUDIO LOGIC
# =========================
class AudioLogic:
    def __init__(self):
        self.is_running = False
        self.model = None
        self.last_client_msg = ""
        self.speech_lock = threading.Lock()
        self.conversation_history = []
        self.extracted_cin = None

    def log(self, text, tag="sys"):
        print(f"[{tag}] {text}")
        try:
            eel.add_log(text, tag)
        except: pass

    def set_status(self, text):
        try:
            eel.update_phone_status(text)
        except: pass

    def start_call(self):
        if not self.model:
            threading.Thread(target=self.load_model).start()
        else:
            self.start_loop()

    def load_model(self):
        self.log("⏳ Chargement Whisper small...", "sys")
        self.model = whisper.load_model("small")
        #self.log("⏳ Chargement Whisper base (plus rapide)...", "sys")
        #self.model = whisper.load_model("base")
        self.log("✅ Whisper chargé", "sys")
        self.start_loop()

    def start_loop(self):
        self.is_running = True
        # Generate a random integer session ID for DB compatibility
        self.session_id = str(random.randint(100000, 999999))
        self.log(f"🆔 Session ID: {self.session_id}", "sys")
        threading.Thread(target=self.audio_loop).start()

    def stop_call(self):
        self.is_running = False
        self.set_status("Raccroché")
        # Déclenchement de l'envoi de l'email de résumé
        threading.Thread(target=self.send_summary_email).start()

    def send_summary_email(self):
        if not self.conversation_history:
            self.log("ℹ️ Pas d'historique de conversation, envoi d'email annulé.", "sys")
            return

        self.log("📝 Génération du résumé de la conversation...", "sys")
        
        try:
            state = {"messages": self.conversation_history}
            summary_data = reformulate_history_to_email(state, self.extracted_cin)
            
            subject = summary_data.get("subject", "Suivi de votre dossier")
            message_body = summary_data.get("body", "")
            
            if self.extracted_cin and self.extracted_cin != "null":
                self.log(f"📧 Envoi de l'email de suivi pour le CIN: {self.extracted_cin}...", "sys")
                from tools.send_communication import send_communication
                result = send_communication(
                    cin=self.extracted_cin,
                    canal="EMAIL",
                    message=message_body,
                    subject=subject
                )
                status_msg = result.get('status') or result.get('error') or "Succès"
                self.log(f"📧 Résultat envoi: {status_msg}", "sys")
            else:
                self.log("⚠️ Aucun CIN trouvé dans la conversation, impossible d'envoyer l'email de suivi.", "sys")
                
        except Exception as e:
            self.log(f"❌ Erreur lors du résumé/envoi de l'email: {e}", "sys")

    # =========================
    # AUDIO LOOP
    # =========================
    def audio_loop(self):
        self.log("--- Début appel ---", "sys")
        while self.is_running:
            audio_file = self.record_audio_chunk()
            if not audio_file: continue

            self.set_status("📝 Transcription...")
            result = self.model.transcribe(audio_file, language="fr", no_speech_threshold=0.6, beam_size=1, temperature=0)
            os.remove(audio_file)

            text = result["text"].strip()
            if not text or text == self.last_client_msg: continue
            self.last_client_msg = text

            self.log(f"Client (Whisper): {text}", "user")
            self.conversation_history.append(HumanMessage(content=text))

            # =========================
            # LLM GUARD
            # =========================
            self.set_status("🧠 Analyse LLM...")
            decision = llm_guard_decision(text)

            # Mise à jour du CIN si extrait
            if decision.get("extracted_data", {}).get("cin"):
                self.extracted_cin = decision["extracted_data"]["cin"]

            if self.extracted_cin:
                self.extracted_cin = re.sub(r'[^a-zA-Z0-9]', '', self.extracted_cin).lower()
                decision["extracted_data"]["cin"] = self.extracted_cin.strip()


            # 🔹 PRINT pour debug / reformulation
            print("=== LLM REFORMULATION ===")
            print(json.dumps(decision, indent=2, ensure_ascii=False))
            print("==========================")

            if decision["action"] == "ask_client":
                if self.is_running:
                    self.log(f"Agent: {decision['content']}", "agent")
                    self.speak_text(decision["content"])
                continue

            # =========================
            # SEND TO SERVER
            # =========================
            payload = {
                "message": decision["content"],
                "extracted_data": decision["extracted_data"],
                "session_id": self.session_id
            }

            # Analyser si c'est une salutation courte pour éviter le message d'attente
            clean_txt = decision["content"].strip().lower()
            for p in [".", ",", "!", "?"]:
                clean_txt = clean_txt.replace(p, "")
            words = clean_txt.split()
            greetings = {"bonjour", "bonsoir", "salut", "allo", "revoir", "bye", "merci", "oui", "non", "ok", "d'accord", "bientôt"}
            is_greeting = (len(words) <= 4) and any(w in greetings for w in words)

            # Timer de 3 secondes pour message d'attente prolongée
            stop_wait_event = threading.Event()

            def long_wait_worker():
                if not stop_wait_event.wait(20): # 13s wait ensures >7s silence after the first message (~4s)
                    if self.is_running and not stop_wait_event.is_set():
                        self.speak_text("Je recherche les informations nécessaires, merci de patienter encore un instant.")

            threading.Thread(target=long_wait_worker).start()

            self.set_status("🤖 Serveur...")
            
            # Message d'attente initial (non bloquant pour fluidité)
            if self.is_running and not is_greeting:
                threading.Thread(target=self.speak_text, args=("Ok monsieur, merci de patienter quelques instants.",)).start()

            try:
                resp = requests.post(SERVER_URL, json=payload)
                stop_wait_event.set() # Annuler le second message si réponse reçue
                # sd.stop() supprimé pour laisser finir la phrase en cours

                agent_resp = resp.json().get("response", "")
                if self.is_running:
                    self.log(f"Agent: {agent_resp}", "agent")
                    self.conversation_history.append(AIMessage(content=agent_resp))
                    self.speak_text(agent_resp, pre_pause_seconds=3)
            except Exception as e:
                stop_wait_event.set()
                sd.stop()
                self.log(f"Erreur serveur: {e}", "sys")
                self.stop_call()

        self.log("--- Fin appel ---", "sys")

    # =========================
    # SPEAK TEXT
    # =========================
    def speak_text(self, text, pre_pause_seconds=0):
        if not self.is_running:
            self.log("🔇 TTS annulé (appel raccroché)", "sys")
            return
        if not tts_client: return

        try:
            self.log("🔊 Agent parle...", "sys")
            response = tts_client.audio.speech.create(
                model="tts-1",
                voice="alloy",
                input=text,
                speed=1.2,
                response_format="wav"
            )

            if not self.is_running:
                return

            # Generate temp file
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_name = tmp.name
            tmp.close() # Close handle immediately to avoid WinError 32

            with open(tmp_name, "wb") as f:
                for c in response.iter_bytes(): f.write(c)

            if not self.is_running:
                os.remove(tmp_name)
                return

            wav = wavio.read(tmp_name)
            
            with self.speech_lock:
                if pre_pause_seconds > 0:
                    time.sleep(pre_pause_seconds)
                sd.play(wav.data, wav.rate)
                sd.wait()
                
            os.remove(tmp_name)

        except Exception as e:
            self.log(f"❌ Erreur TTS: {e}", "sys")

    # =========================
    # RECORD AUDIO
    # =========================
    def record_audio_chunk(self, max_duration=15, fs=16000):
        chunk_samples = int(0.1 * fs)
        audio = []
        silence = 0
        spoken = False
        try:
            with sd.InputStream(samplerate=fs, channels=1, dtype="float32") as stream:
                for _ in range(int(max_duration/0.1)):
                    if not self.is_running: break
                    chunk, _ = stream.read(chunk_samples)
                    audio.append(chunk)
                    rms = np.sqrt(np.mean(chunk**2))
                    if rms > SILENCE_THRESHOLD:
                        spoken = True
                        silence = 0
                    else:
                        silence += 0.1
                    # Réduction du temps de silence pour détecter la fin de phrase plus vite (0.8s vs 1.5s)
                    if spoken and silence > 0.8: break #1.5

            if not spoken: return None
            data = np.concatenate(audio)
            
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp.close() # Close handle immediately to avoid WinError 32
            
            wavio.write(tmp.name, data, fs, sampwidth=2)
            return tmp.name
        except:
            return None

# =========================
# EEL
# =========================
logic = AudioLogic()

@eel.expose
def start_python_call():
    logic.start_call()

@eel.expose
def stop_python_call():
    logic.stop_call()

if __name__ == "__main__":
    eel.init(os.path.dirname(os.path.abspath(__file__)))
    eel.start("index.html", size=(1280, 850), port=8888)
