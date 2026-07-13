# filtering.py
"""Filtering Module
This module provides functions to filter text chunks based on semantic similarity and interact with a language model to answer questions.
It uses SentenceTransformers for embedding and FAISS for efficient similarity search.
It also includes a function to send prompts to a local LLM API and retrieve answers.
"""


#-----------------------------------------------------------------------------------------------
# IMPORTS
#-----------------------------------------------------------------------------------------------
from sentence_transformers import SentenceTransformer, util

# Chargement du modèle d'embeddings
embedding_model = SentenceTransformer('dangvantuan/sentence-camembert-large')

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