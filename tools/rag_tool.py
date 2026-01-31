from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain.tools import tool
from typing import Optional, Tuple
import os

PERSIST_DIRECTORY = r"C:\Users\AGA Gaming\Downloads\raghakathon\smallsmall\rag\chromadb"
COLLECTION_NAME = "cnp_faqs"
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
SCORE_THRESHOLD = 2 

def load_vectorstore():

    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME)
    vectordb = Chroma(
        collection_name=COLLECTION_NAME,
        persist_directory=PERSIST_DIRECTORY,
        embedding_function=embeddings
    )
    
    return vectordb


@tool
def rag_tool(query: str, k: int = 1, threshold: float = SCORE_THRESHOLD) -> Optional[Tuple[str, dict]]:
    """RAG tool pour les FAQ :
    - Cherche dans le vectorstore
    - Retourne la meilleure réponse si le score est au-dessous du seuil 
    - Sinon, retourne None pour escalade
    """
    print(f"RAG Tool - Query: {query}")
    
    vectorstore = load_vectorstore()

    
    results = vectorstore.similarity_search_with_score(query, k=k)
    if not results:
        return None
    
    print(f"RAG Tool - Retrieved {results} results.")

    doc, score = results[0]
    print(f"Top result score: {score} (Threshold: {threshold})")
    
    if score >= threshold:
        print(f"❌ Result rejected (Score {score} >= {threshold})")
        return None

    return doc.page_content, doc.metadata

# print(rag_tool("C est quoi assurance de la vie", k=3, threshold=SCORE_THRESHOLD))