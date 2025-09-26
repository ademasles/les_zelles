# summarization.py
"""Summarization module for processing text chunks and generating summaries.
This module provides functions to summarize text chunks using a language model and to generate global summaries.
"""
# SPDX-FileCopyrightText: 2025 Anton Demasles <

#-----------------------------------------------------------------------------------------------
# IMPORTS
#-----------------------------------------------------------------------------------------------
import requests
import os

url = os.getenv("OLLAMA_HOST", "http://ollama:11434")


def summarize_chunk(chunk, model="mistral", url=url):
    """
    Summarize a single text chunk using a language model.
    :param chunk: Dictionary containing the text chunk to summarize.
    :param model: The model to use for summarization (default is "mistral").
    :param url: The URL of the local LLM API.
    :return: The summarized text.
    """
    full_url = url.rstrip("/") + "/api/generate"
    prompt = f"""
    Tu es un expert en menuiserie du bâtiment. Ton rôle est d'analyser un extrait de CCTP et de produire un résumé fluide, professionnel et directement utile à un bureau d'études.

    Objectif : extraire uniquement les informations techniques réellement présentes dans le texte, utiles à l'étude et au chiffrage (ex : matériaux, coloris, vitrage, pose, normes, performances, accessoires, etc.).

    Contraintes :
    - Utilise un style narratif naturel, sans liste à puces
    - Ne commente pas l'absence d'information
    - Ne complète rien par déduction ou généralisation
    - Si plusieurs informations sont présentes, exprime-les dans des phrases distinctes, chacune compréhensible seule

    Contenu à analyser :
    {chunk["text"]}
    """.strip()


    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }

    try:
        response = requests.post(full_url, json=payload)
        response.raise_for_status()
        return response.json()["response"].strip()
    except Exception as e:
        print(f"❌ Erreur appel Mistral : {e}")
        return "Erreur"

#-----------------------------------------------------------------------------------------------
def summarize_cctp(chunks, verbose=True, model="mistral"):
    """
    Summarize a list of text chunks into a coherent summary.
    :param chunks: List of dictionaries containing text chunks to summarize.
    :param verbose: Whether to print progress messages (default is True).
    :param model: The model to use for summarization (default is "mistral
    :return: List of dictionaries with summarized chunks.
    """
    all_summaries = []
    for i, chunk in enumerate(chunks):
        if verbose:
            print(f"📄 Résumé du chunk {i+1}/{len(chunks)} - page {chunk.get('page_number', '?')}...")
        
        summary = summarize_chunk(chunk)  # Fonction que tu as déjà
        if summary and summary.strip().lower() not in ["non pertinent", "erreur"]:
            all_summaries.append({
                "doc_name": chunk["doc_name"],
                "chunk_id": chunk.get("chunk_id"),
                "page_number": chunk["page_number"],
                "summary": summary.strip(),
                "start_char": chunk.get("start_char"),
                "end_char": chunk.get("end_char"),
                "chunk_text": chunk["raw_text"]
            })

    return all_summaries

#-----------------------------------------------------------------------------------------------
def summarize_global(all_summaries, model="mistral"):
    """
    Generate a global summary from all summarized chunks.
    :param all_summaries: List of dictionaries containing summarized chunks.
    :param model: The model to use for generating the global summary (default is "mistral").
    :return: A single summarized text.
    """
    text = "\n".join([s["summary"] for s in all_summaries])
    return summarize_chunk({"text": text}, model=model)


