"""Compat layer — thin async functions that bridge legacy main.py routes to new services.

EmbeddingService and FaissVectorStore are module-level singletons initialized once.
compat_upload embeds chunks and adds them to FAISS so compat_query can retrieve them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.llm.ollama_client import OllamaClient
from app.preprocessing.markdown.markdown_cleaner import clean_markdown
from app.preprocessing.markdown.section_splitter import chunk_markdown
from app.preprocessing.parsers.fallback import parse_with_fallback
from app.rag.embeddings import EmbeddingService
from app.rag.prompts import build_summary_prompt
from app.rag.retriever import Retriever
from app.rag.vector_store import FaissVectorStore
from app.storage.file_store import save_markdown, save_parsed_json, save_raw

documents: dict[str, Any] = {}
query_results_store: dict[str, Any] = {}

embedding_service = EmbeddingService()
vector_store = FaissVectorStore()
retriever = Retriever(embedding_service, vector_store)


async def compat_upload(file_path: Path, doc_id: str) -> dict[str, Any]:
    if doc_id in documents:
        msg = "Document ID already exists"
        raise ValueError(msg)

    parsed = parse_with_fallback(file_path)

    folder = settings.storage_dir / doc_id
    folder.mkdir(parents=True, exist_ok=True)
    save_raw(doc_id, doc_id, file_path.name, file_path.read_bytes())
    save_markdown(doc_id, doc_id, parsed.markdown)
    save_parsed_json(doc_id, doc_id, parsed.structured_data)

    cleaned = clean_markdown(parsed.markdown)
    chunks = chunk_markdown(cleaned, document_id=doc_id)

    texts = [c["text"] for c in chunks]
    embeddings = embedding_service.embed_chunks(texts)
    vector_store.add_chunks(
        chunk_ids=[doc_id] * len(chunks),
        embeddings=embeddings,
        metadata=chunks,
    )

    llm = OllamaClient()
    prompt, _ = build_summary_prompt(cleaned)
    summary = llm.generate(prompt)

    documents[doc_id] = chunks

    return {
        "doc_id": doc_id,
        "filename": file_path.name,
        "summary": summary,
        "num_chunks": len(chunks),
        "status": "indexed",
        "query": f"Document {doc_id} indexe avec succes.",
    }


async def compat_query(doc_id: str, question: str) -> dict[str, Any]:
    if doc_id not in documents:
        return {"error": "Document non trouve"}

    from app.services.rag_service import answer_question

    llm = OllamaClient()
    result = await answer_question(question, retriever, llm, document_id=doc_id)

    return {
        "question": question,
        "best_answer": result["answer"],
        "alternatives": [
            {
                "response": c.get("quote", ""),
                "score": c.get("score", 0),
                "summary": "",
                "page_number": c.get("page_start"),
                "chunk_id": c.get("chunk_id", ""),
                "chunk_text": c.get("quote", ""),
            }
            for c in result.get("citations", [])
        ],
    }


async def compat_run_queries(doc_id: str) -> dict[str, Any]:
    if doc_id not in documents:
        msg = "Document non trouve"
        raise ValueError(msg)

    queries_file = Path(settings.queries_path)
    if not queries_file.exists():
        return {}

    queries: dict[str, str] = json.loads(queries_file.read_text(encoding="utf-8"))
    results: dict[str, Any] = {}
    for q_label, q_text in queries.items():
        results[q_label] = await compat_query(doc_id, q_text)

    query_results_store[doc_id] = results
    return results


async def compat_summary(doc_id: str) -> dict[str, str]:
    if doc_id not in documents:
        return {"error": "Document non trouve"}

    chunks = documents[doc_id]
    all_text = "\n".join(c.get("text", "") for c in chunks)
    prompt, _ = build_summary_prompt(all_text)
    llm = OllamaClient()
    summary = llm.generate(prompt)
    return {"summary": summary}


def compat_save_project(doc_id: str, name: str, results_json: str) -> dict[str, str]:
    from database.database import Answer, Project, Query, SessionLocal

    results = json.loads(results_json)
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == doc_id).first()
        if not project:
            new_proj = Project(id=doc_id, name=name)
            db.add(new_proj)
            db.commit()
        else:
            return {"message": "Deja existant"}

        for question_text, result in results.items():
            new_query = Query(
                project_id=doc_id,
                question=question_text,
                best_answer=result.get("best_answer"),
            )
            db.add(new_query)
            db.commit()
            db.refresh(new_query)

            for alt in result.get("alternatives", []):
                answer = Answer(
                    query_id=new_query.id,
                    response=alt.get("response"),
                    score=alt.get("score"),
                    summary=alt.get("summary"),
                    page_number=alt.get("page_number"),
                    chunk_id=alt.get("chunk_id"),
                    excerpt=alt.get("chunk_text"),
                )
                db.add(answer)
            db.commit()

        return {"message": "Projet et questions sauvegardes avec succes"}
    finally:
        db.close()


def compat_store_feedback(question: str, response: str, score: float) -> dict[str, str]:
    with open("feedback_dataset.jsonl", "a", encoding="utf-8") as f:
        json.dump({"question": question, "response": response, "score": score}, f)
        f.write("\n")
    return {"status": "ok"}
