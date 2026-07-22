"""Compat — delegates to new RAG service for question answering."""

from __future__ import annotations

from typing import Any

from app.llm.ollama_client import OllamaClient
from app.rag.embeddings import EmbeddingService


def filter_chunks(summaries: list[dict], query: str, top_k: int = 5) -> list[dict]:
    """Legacy-compat: semantic filter using embeddings."""
    import numpy as np

    emb = EmbeddingService()
    query_vec = emb.embed_query(query)
    texts = [s.get("summary", s.get("text", "")) for s in summaries]
    if not texts:
        return []

    vecs = emb.embed_chunks(texts)
    scores = np.dot(vecs, query_vec) / (
        np.linalg.norm(vecs, axis=1) * np.linalg.norm(query_vec) + 1e-10
    )

    top_indices = np.argsort(scores)[-top_k:][::-1]
    return [{**summaries[i], "score": float(scores[i])} for i in top_indices]


def ask_llm(prompt: str, model: str | None = None, url: str | None = None) -> str | None:
    from app.core.config import settings

    client = OllamaClient(
        base_url=url or settings.ollama_base_url,
        model=model or settings.llm_model,
    )
    try:
        return client.generate(prompt)
    except Exception as e:
        print(f"LLM error: {e}")
        return None


def chat_llm(
    question: str, summaries: list, model: str | None = None, top_k: int = 5
) -> tuple[str, dict]:
    relevant = filter_chunks(summaries, question, top_k=top_k)
    best_answer = None
    best_score = -1
    answers: dict[str, list] = {"response": [], "score": [], "chunk": []}

    for chunk in relevant:
        chunk_text = chunk.get("summary", chunk.get("text", "")).strip()
        if not chunk_text:
            continue

        prompt = (
            f"Tu es un assistant expert en menuiserie. Voici un extrait de CCTP technique :\n\n"
            f"{chunk_text}\n\n"
            f"Consigne :\n"
            f"Reponds precisement a la question suivante uniquement si l'information "
            f"est explicitement presente dans le texte.\n"
            f"Sinon, reponds simplement par : RAS.\n\n"
            f"Question : {question}\n\n"
            f"Reponse :"
        )

        response = ask_llm(prompt, model=model)
        if response and "ras" not in response.lower():
            import numpy as np

            emb = EmbeddingService()
            qv = emb.embed_query(question)
            rv = emb.embed_query(response)
            score = float(np.dot(qv, rv) / (np.linalg.norm(qv) * np.linalg.norm(rv) + 1e-10))

            answers["response"].append(response.strip())
            answers["score"].append(score)
            answers["chunk"].append(chunk)

            if score > best_score:
                best_answer = response.strip()
                best_score = score

    return best_answer or "Non trouve", answers


def answer_queries(
    queries: dict, summaries: list, top_k: int = 5, model: str | None = None
) -> dict[str, Any]:
    results = {}
    top_k = min(top_k, len(summaries)) if summaries else 1

    for display_question, query in queries.items():
        best_answer, answers = chat_llm(query, summaries, model=model, top_k=top_k)

        items = []

        responses = answers.get("response", [])
        scores = answers.get("score", [])
        chunks = answers.get("chunk", [])

        for resp, sc, chunk in zip(responses, scores, chunks, strict=False):
            if not chunk.get("chunk_text", "").strip():
                continue
            text_len = len(chunk["chunk_text"])
            start = min(chunk.get("start_char", 0), text_len)
            end = min(chunk.get("end_char", text_len), text_len)

            items.append(
                {
                    "response": resp,
                    "summary": chunk.get("summary", "").strip(),
                    "score": round(float(sc), 3),
                    "doc_name": chunk.get("doc_name"),
                    "page_number": chunk.get("page_number"),
                    "chunk_id": chunk.get("chunk_id"),
                    "excerpt": chunk.get("chunk_text", "").strip(),
                    "start_char": start,
                    "end_char": end,
                }
            )

        results[display_question] = {
            "question": display_question,
            "best_answer": best_answer,
            "alternatives": items,
        }

    return results
