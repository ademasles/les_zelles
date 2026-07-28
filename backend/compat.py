"""Compat layer — thin async functions that bridge legacy main.py routes to new services.

EmbeddingService and FaissVectorStore are module-level singletons initialized once.
compat_upload embeds chunks and adds them to FAISS so compat_query can retrieve them.
"""

from __future__ import annotations

import json
from typing import Any

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
