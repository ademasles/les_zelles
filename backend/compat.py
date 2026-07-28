"""Compat layer — thin async functions that bridge legacy main.py routes to new services.

EmbeddingService and FaissVectorStore are module-level singletons initialized once.
compat_upload embeds chunks and adds them to FAISS so compat_query can retrieve them.
"""

from __future__ import annotations

import json
import shutil
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
from app.storage.file_store import save_markdown, save_parsed_json, save_raw

query_results_store: dict[str, Any] = {}


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

