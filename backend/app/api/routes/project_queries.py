"""Legacy-compat routes for frontend project queries.

These bridge the gap between the old frontend calling /project_queries/
and the new backend architecture.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request

from database.database import Answer, Project, Query, SessionLocal

router = APIRouter(prefix="/project_queries", tags=["project_queries"])


@router.get("/{doc_id}")
def get_project_queries(doc_id: str):
    """Return all questions and answers for a given project (legacy compat)."""
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == doc_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Projet non trouvé")

        queries = db.query(Query).filter(Query.project_id == doc_id).all()
        output: dict = {}

        for query in queries:
            answers = db.query(Answer).filter(Answer.query_id == query.id).all()
            alternatives = [
                {
                    "response": ans.response,
                    "score": ans.score,
                    "summary": ans.summary,
                    "page_number": ans.page_number,
                    "chunk_id": ans.chunk_id,
                    "chunk_text": ans.excerpt,
                }
                for ans in answers
            ]
            output[query.question] = {
                "question": query.question,
                "best_answer": query.best_answer,
                "alternatives": alternatives,
            }

        return output
    finally:
        db.close()


@router.post("/add")
async def add_query_to_project(request: Request):
    """Add a user-defined question and its AI answers to a project (legacy compat)."""
    form_data = await request.form()
    doc_id = form_data.get("doc_id")
    question = form_data.get("question")
    result_json = form_data.get("result")

    if not all([doc_id, question, result_json]):
        raise HTTPException(status_code=400, detail="Requête incomplète")

    try:
        result = json.loads(result_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="JSON mal formé") from None

    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == doc_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Projet non trouvé")

        new_query = Query(
            project_id=doc_id,
            question=question,
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
        return {"message": f"Question '{question}' ajoutée au projet {doc_id}"}
    finally:
        db.close()
