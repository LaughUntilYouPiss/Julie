import requests
import json

def trigger_mock_escalation():
    url = "http://localhost:8001/escalate"
    
    payload = {
        "session_id": "SESS-TEST-998",
        "cin": "BB051004",
        "resume": "banana",
        "reason": "Sentiment négatif élevé (Colère détectée)",
        "sentiment": "ferhana"
    }

    print(f"🚀 Envoi d'une simulation d'escalade vers {url}...")
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("✅ Succès ! Allez voir votre dashboard sur http://localhost:8001")
            print("L'écran devrait être passé en mode ALERTE ROUGE.")
        else:
            print(f"❌ Erreur {response.status_code}: {response.text}")
    except Exception as e:
        print(f"❌ Impossible de joindre le serveur : {e}")
        print("Vérifiez que 'python dashboard_server.py' est bien lancé sur le port 8001.")

if __name__ == "__main__":
    trigger_mock_escalation()
