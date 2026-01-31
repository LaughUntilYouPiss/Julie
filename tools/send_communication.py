import datetime
import smtplib
import mysql.connector
from email.mime.text import MIMEText
from typing import Optional, Dict, Any
from langchain.tools import tool

# --- CONFIGURATION (À REMPLIR PAR L'UTILISATEUR) ---

# Configuration de la base de données
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "1234",
    "database": "assurances"
}

# Configuration Email (SMTP)
SMTP_CONFIG = {
    "server": "smtp.gmail.com",
    "port": 587,
    "user": "dephylleum@gmail.com",
    "password": "gomuacgzfpvudqyz"
}


# --- CONFIGURATION SMS (DÉSACTIVÉE) ---
# TWILIO_CONFIG = {
#     "account_sid": "votre_sid",
#     "auth_token": "votre_token",
#     "from_number": "+123456789"
# }

# --- FONCTIONS RECHERCHE CLIENT ---

def get_client_info_by_cin(cin: str) -> Optional[Dict[str, Any]]:
    """Récupère les informations du client via son CIN."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        query = "SELECT ID_CLIENT, EMAIL, TELEPHONE, NOM, PRENOM FROM CLIENT WHERE CIN = %s"
        cursor.execute(query, (cin,))
        result = cursor.fetchone()
        return result
    except mysql.connector.Error as err:
        print(f"Erreur recherche CIN: {err}")
        return None
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

# --- FONCTIONS D'ENVOI ---


# def send_real_sms(to_number: str, body: str) -> bool:
#     """Envoie un SMS réel via Twilio."""
#     try:
#         from twilio.rest import Client
#         client = Client(TWILIO_CONFIG['account_sid'], TWILIO_CONFIG['auth_token'])
#         message = client.messages.create(
#             body=body,
#             from_=TWILIO_CONFIG['from_number'],
#             to=to_number
#         )
#         return True
#     except Exception as e:
#         print(f"Erreur envoi SMS: {e}")
#         return False

# --- LOGIQUE DATABASE ---

def record_message_in_db(
    canal: str, 
    contenu: str, 
    client_id: Optional[int] = None,
    session_id: Optional[int] = None,
    direction: str = "SORTANT"
) -> Optional[int]:
    """Enregistre le message dans la base de données."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()

        insert_query = """
            INSERT INTO MESSAGE (ID_CLIENT, ID_SESSION, CANAL, DIRECTION, CONTENU, DATE_ENVOI, STATUT_MESSAGE)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        now = datetime.date.today()
        cursor.execute(insert_query, (client_id, session_id, canal.upper(), direction, contenu, now, "ENVOYE"))
        message_id = cursor.lastrowid

        conn.commit()
        return message_id
    except mysql.connector.Error as err:
        print(f"Erreur MySQL : {err}")
        return None
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

# --- TOOL ---


def send_communication(
    cin: str,
    canal: str,
    message: str,
    sinistre_id: Optional[int] = None,
    subject: Optional[str] = None
) -> Dict[str, Any]:
    """
    Envoie un message RÉEL (Email uniquement actuellement) en cherchant le contact via le CIN du client.
    
    Args:
        cin: Numéro de Carte d'Identité Nationale du client.
        canal: 'EMAIL' (SMS temporairement désactivé).
        message: Le contenu du message.
        sinistre_id: (Optionnel) ID du sinistre lié.
        subject: (Optionnel) Sujet de l'email. Si non fourni, utilise "Suivi de votre dossier".
    """
    canal = canal.upper()
    
    # 1. Recherche du client en base
    client_info = get_client_info_by_cin(cin)
    if not client_info:
        return {"success": False, "error": f"Client avec CIN '{cin}' non trouvé."}

    recipient_contact = None
    
    recipient_contact = client_info.get("EMAIL")
    
    if not recipient_contact:
        return {"success": False, "error": f"Contact ({canal}) non renseigné pour le client {cin}."}

    # 2. Envoi physique
    success = False
    
    # Utilisation du sujet fourni ou du sujet par défaut
    email_subject = subject if subject else "Suivi de votre dossier"
    success = send_real_email(recipient_contact, email_subject, message)
    
    if not success:
        return {"success": False, "error": f"Échec de l'envoi physique via {canal} à {recipient_contact}."}

    # 3. Enregistrement en base de données
    message_id = record_message_in_db(
        canal=canal,
        contenu=message,
        client_id=client_info["ID_CLIENT"]
    )

    if message_id:
        return {
            "success": True,
            "message_id": message_id,
            "client": f"{client_info['PRENOM']} {client_info['NOM']}",
            "status": f"Message envoyé via {canal} à {recipient_contact} et enregistré en base."
        }
    else:
        return {
            "success": True,
            "warning": "Message envoyé, mais échec de l'enregistrement en base.",
            "status": f"Message envoyé via {canal} à {recipient_contact}."
        }
