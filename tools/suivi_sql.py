import mysql.connector
from typing import Optional, List, Dict, Any
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, ToolMessage, AIMessage
import os
import re

# Configuration de la base de données (identique aux autres outils)
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "1234",
    "database": "assurances"
}

SYSTEM_PROMPT = """Tu es un agent SQL spécialisé pour un CALLBOT D’ASSURANCE.

CONTEXTE TECHNIQUE :
- Base de données : MySQL
- Le client est identifié UNIQUEMENT par son CIN
- Le CIN est fourni EXPLICITEMENT dans la question utilisateur
- Toujours utiliser la valeur exacte du CIN fournie
- Ne JAMAIS inventer de CIN
- Ne JAMAIS utiliser de placeholder (?, %s, :cin, etc.)
- N’utiliser QUE des requêtes SELECT
- Les tables SESSION_CALLBOT et MESSAGE sont strictement interdites
- Toute autre requête (INSERT, UPDATE, DELETE, DROP, ALTER) est strictement interdite
- Toutes les requêtes doivent être filtrées pour UN SEUL client

OBJECTIF :
- Générer UNE ou PLUSIEURS requêtes SQL SELECT
- Les requêtes doivent répondre précisément à la question du client
- Utiliser JOIN lorsque nécessaire
- Ne jamais exposer de données d’autres clients
- Si la question est ambiguë ou hors périmètre, générer la requête la plus proche possible

TABLES AUTORISÉES :

CLIENT
- ID_CLIENT, CIN, NOM, PRENOM, EMAIL, TELEPHONE

CONTRAT
- ID_CONTRAT, ID_CLIENT, TYPE_CONTRAT, STATUT, DATE_DEBUT, DATE_FIN, MONTANT_TOTAL

SINISTRE
- ID_SINISTRE, ID_CONTRAT, ID_CALENDRIER, REFERENCE_SINISTRE, STATUT, DATE_SINISTRE, UPDATED_DATE

DOCUMENT
- ID_DOCUMENT, NOM_DOCUMENT, DESCRIPTION

DOCUMENT_MANQUANT
- ID_SINISTRE, ID_DOCUMENT, DATE_DETECTION, STATUT

ECHEANCIER
- ID_ECHEANCE, ID_CONTRAT, DATE_ECHEANCE, MONTANT, STATUT

PAIEMENT
- ID_PAIEMENT, ID_CLIENT, ID_ECHEANCE, DATE_PAIEMENT, MONTANT_PAYE, MODE_PAIEMENT, STATUT

SCHÉMA LOGIQUE :
- CLIENT 1---N CONTRAT
- CONTRAT 1---N SINISTRE
- CONTRAT 1---N ECHEANCIER
- ECHEANCIER 1---N PAIEMENT
- SINISTRE N---N DOCUMENT (via DOCUMENT_MANQUANT)

RÈGLES SQL STRICTES :
1. Toujours filtrer par CLIENT.CIN
2. Toujours utiliser les jointures correctes
3. Ne jamais sélectionner de colonnes inexistantes
4. Utiliser COUNT, SUM, MIN, MAX si pertinent
5. Ne jamais halluciner de tables ou de relations
6. Si une information demandée n’existe pas (ex: conseiller),
   retourner la requête la plus proche possible sur CLIENT

FORMAT DE RÉPONSE :
- Fournir UNIQUEMENT du SQL
- Chaque requête doit commencer par un commentaire SQL (-- ...)
- Ne fournir AUCUN texte hors SQL
- Ne jamais utiliser Markdown

"""

@tool
def search_db_info(query: str, cin: str) -> Dict[str, Any]:
    """
    Recherche des informations dans la base de données MySQL pour répondre à une question client.
    Génère et exécute des requêtes SQL sécurisées basées sur la question.
    
    Args:
        query: La question ou demande d'information du client (ex: "Combien de contrats ai-je ?")
        cin: Le CIN du client authentifié (ex: "AB123456").
        
    Returns:
        Dict contenant les résultats de la recherche ou un message d'erreur.
    """
    llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0)

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=f"""
        Question client : {query}
        CIN du client : {cin}
        """
                )
            ]

    response = llm.invoke(messages)
    sql_content = response.content

    cleaned_sql = re.sub(r"```sql|```", "", sql_content).strip()
    queries = [q.strip() for q in cleaned_sql.split(';') if q.strip()]

    results = {
        "generated_sql": cleaned_sql,
        "data": []
    }

    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)

    for idx, q_text in enumerate(queries):
        sql_check = re.sub(r"^--.*\n", "", q_text, flags=re.MULTILINE).strip().upper()

        if not sql_check.startswith("SELECT"):
            continue

        try:
            cursor.execute(q_text)
            rows = cursor.fetchall()

            serializable_rows = []
            for row in rows:
                serializable_rows.append({
                    k: (v.isoformat() if hasattr(v, 'isoformat') else str(v))
                    for k, v in row.items()
                })

            results["data"].append({
                "query_index": idx,
                "rows": serializable_rows
            })

        except mysql.connector.Error as err:
            results["data"].append({
                "query_index": idx,
                "error": str(err)
            })

    cursor.close()
    conn.close()

    return results