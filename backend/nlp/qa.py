# qa.py
"""Question Answering Module
This module provides functions to filter text chunks based on semantic similarity and interact with a language model to answer questions.
It uses SentenceTransformers for embedding and FAISS for efficient similarity search.
It also includes a function to send prompts to a local LLM API and retrieve answers.
"""


#-----------------------------------------------------------------------------------------------
# IMPORTS
#-----------------------------------------------------------------------------------------------
import requests
from sentence_transformers import SentenceTransformer, util#, CrossEncoder
import os
import torch
MAX_CONTEXT_TOKENS = 3000
#embedding_model = SentenceTransformer('dangvantuan/sentence-camembert-large')
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
url = os.getenv("OLLAMA_HOST", "http://ollama:11434")


#-----------------------------------------------------------------------------------------------
# FONCTIONS
#-----------------------------------------------------------------------------------------------
def filter_chunks(summaries, query, top_k=5):
    """
    Filter text chunks based on semantic similarity to the query.
    :param summaries: List of dictionaries with text chunks to filter.
    :param query: The query string to filter chunks against.
    :param top_k: Number of top results to return.
    :return: List of filtered chunks with their scores.
    """
    top_k = min(top_k, len(summaries))
    query_embedding = embedding_model.encode(query, convert_to_tensor=True)
    
    summary_texts = [chunk["summary"] for chunk in summaries]
    summary_embeddings = embedding_model.encode(summary_texts, convert_to_tensor=True)

    hits = util.semantic_search(query_embedding, summary_embeddings, top_k=top_k)[0]

    # Retourner les chunks enrichis originaux avec score facultatif
    filtered = []
    for hit in hits:
        chunk = summaries[hit['corpus_id']]
        chunk_with_score = chunk.copy()
        chunk_with_score["score"] = float(hit["score"])  # Ajout de la pertinence
        filtered.append(chunk_with_score)

    return filtered

#-----------------------------------------------------------------------------------------------
def ask_llm(prompt, model="mistral", url=url):
    """
    Send a prompt to the local LLM API and return the response.
    :param prompt: The text prompt to send to the LLM.
    :param model: The model to use for the LLM (default is "mistral").
    :param url: The URL of the local LLM API.
    :return: The response text from the LLM.
    """
    full_url = url.rstrip('/') + "/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }

    try:
        response = requests.post(full_url, json=payload, timeout=120)
        response.raise_for_status()
        return response.json().get("response", "").strip()
    except Exception as e:
        print(f"❌ Erreur en appelant Mistral : {e}")
        return None
#-----------------------------------------------------------------------------------------------

#cross_encoder = CrossEncoder("dangvantuan/CrossEncoder-camembert-large", max_length=512)
def chat_llm(question: str, summaries: list, model="mistral", top_k=5):
    """
    Interact with the LLM to answer a question based on filtered text chunks.
    :param question: The question to ask the LLM.
    :param summaries: List of text chunks to filter and use for answering.
    :param model: The model to use for the LLM (default is "mistral").
    :param top_k: Number of top chunks to consider for answering.
    :return: The best answer from the LLM and a dictionary of all answers with their scores.
    """
    top_k = min(top_k, len(summaries))
    # Étape 1 : filtrer les chunks les plus proches sémantiquement
    relevant_summaries = filter_chunks(summaries, question, top_k=top_k)
    
    best_answer = None
    best_score = -1
    answers = {"response": [], "score": [], "chunk": []}

    for chunk in relevant_summaries:
        # Utilise le chunk text complet, pas seulement le résumé
        chunk_text = chunk.get("summary", "").strip()
        doc_name = chunk.get("doc_name", "unknown")
        page_number = chunk.get("page_number", "?")

        prompt = f"""Tu es un assistant expert en menuiserie. Voici un extrait de CCTP technique :

{chunk_text}

Consigne :  
Réponds précisément à la question suivante **uniquement si** l'information est explicitement présente dans le texte.  
Sinon, réponds simplement par : "RAS".

Question : {question}

Réponse :
"""

        try:
            response = ask_llm(prompt, model=model)
            print(f"Réponse LLM OK")
        except Exception as e:
            print(f"❌ Erreur LLM : {e}")
            continue

        if response and "ras" not in response.lower():

            try:
                #score = cross_encoder.predict([(question, response)])[0]
                score = util.cos_sim(
                embedding_model.encode(question, convert_to_tensor=True),
                embedding_model.encode(response, convert_to_tensor=True)
            ).item()
            except RuntimeError as e:
                print(f"❌ Erreur de calcul de similarité : {e}")
                continue
                
            answers["response"].append(response.strip())
            answers["score"].append(float(score))
            answers["chunk"].append(chunk)

            if score > best_score:
                best_answer = response.strip()
                best_score = score

    return best_answer or "Non trouvé", answers

#-----------------------------------------------------------------------------------------------
def answer_queries(queries: dict, summaries: list, top_k=5, model="mistral"):
    """
    Answer a set of queries using the provided text chunks.
    :param queries: Dictionary of queries where keys are query IDs and values are display questions.
    :param summaries: List of text chunks to filter and use for answering.
    :param top_k: Number of top chunks to consider for each query.
    :param model: The model to use for the LLM (default is "mistral").
    :return: Dictionary of results with answers and additional information.
    """
    results = {}
    top_k = min(top_k, len(summaries))
    for display_question, query in queries.items():
        print(f"\n🔍 Question : {display_question} ?")


        best_answer, answers = chat_llm(query, summaries, model=model, top_k=top_k)

        # Vérification préventive
        if not (len(answers["response"]) == len(answers["score"]) == len(answers["chunk"])):
            print(f"❌ Format d'alignement incorrect pour la question : {display_question}")
            continue

        items = []
        for resp, sc, chunk in sorted(zip(
            answers["response"],
            answers["score"],
            answers["chunk"]
        ), key=lambda x: x[1], reverse=True):
            if not chunk.get("chunk_text", "").strip():
                continue  # évite les textes vides

            text_len = len(chunk["chunk_text"])
            start = min(chunk.get("start_char", 0), text_len)
            end = min(chunk.get("end_char", text_len), text_len)

            items.append({
                "response": resp,
                "summary": chunk.get("summary", "").strip(),
                "score": round(float(sc), 3),
                "doc_name": chunk.get("doc_name"),
                "page_number": chunk.get("page_number"),
                "chunk_id": chunk.get("chunk_id"),
                "excerpt": chunk.get("chunk_text", "").strip(),
                "start_char": start,
                "end_char": end
            })


        results[display_question] = {
            "question": display_question,
            "best_answer": best_answer,
            "alternatives": items
        }

    return results

