"""Projects routes — CRUD and query management for projects."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from database.database import Answer, Project, Query, SessionLocal

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("/")
def get_projects() -> list[dict[str, Any]]:
    """Return all saved projects."""
    db = SessionLocal()
    try:
        projects = db.query(Project).all()
        return [p.as_dict() for p in projects] or []
    finally:
        db.close()


@router.post("/")
async def save_project(request: Request) -> dict[str, str]:
    """Create a new project from a JSON body with name."""
    body = await request.json()
    name = body.get("name")

    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    db = SessionLocal()
    try:
        new_project = Project(name=name)
        db.add(new_project)
        db.commit()
        db.refresh(new_project)
        return {"message": f"Projet '{name}' enregistre", "project_id": new_project.id}
    finally:
        db.close()


@router.get("/{project_id}")
def get_project(project_id: str) -> dict[str, Any]:
    """Return a single project by ID."""
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Projet non trouve")
        return project.as_dict()
    finally:
        db.close()


@router.delete("/{project_id}")
def delete_project(project_id: str) -> dict[str, str]:
    """Delete a project and its associated queries/answers."""
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Projet non trouve")
        db.delete(project)
        db.commit()
        return {"message": "Projet supprime avec succes"}
    finally:
        db.close()


@router.get("/{project_id}/queries")
def get_project_queries(project_id: str) -> dict[str, Any]:
    """Return all questions and answers for a given project."""
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Projet non trouve")

        queries = db.query(Query).filter(Query.project_id == project_id).all()
        output: dict[str, Any] = {}

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


@router.post("/{project_id}/queries")
async def add_query_to_project(project_id: str, request: Request) -> dict[str, str]:
    """Add a user-defined question and its AI-generated answers to a project."""
    form_data = await request.form()
    question = form_data.get("question")
    result_json = form_data.get("result")

    if not all([question, result_json]):
        raise HTTPException(status_code=400, detail="Requete incomplete")

    try:
        result = json.loads(result_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="JSON mal forme dans result") from None

    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Projet non trouve")

        new_query = Query(
            project_id=project_id,
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
        return {"message": f"Question '{question}' ajoutee au projet {project_id}"}
    finally:
        db.close()
