"""Routes for asking questions and running predefined queries against documents."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_retriever
from app.database.session import get_db
from app.rag.retriever import Retriever
from app.repositories.document_repository import DocumentRepository
from app.services.question_service import QuestionService

router = APIRouter()


@router.post("/query/")
async def query(
    doc_id: str = Form(...),
    question: str = Form(...),
    db: AsyncSession = Depends(get_db),
    retriever: Retriever = Depends(get_retriever),
):
    """Ask a question about a document."""
    try:
        doc_repo = DocumentRepository(db)
        doc = await doc_repo.get(doc_id)
        if not doc or not doc.project_id:
            raise HTTPException(
                status_code=404, detail="Document or associated project not found"
            )

        question_service = QuestionService(db, retriever)
        result = await question_service.ask_question_on_document(
            question_text=question, document_id=doc_id, project_id=doc.project_id
        )

        # Reformat to legacy response structure for the frontend
        formatted_result = {
            "question": question,
            "best_answer": result.get("answer"),
            "alternatives": [
                {
                    "response": c.get("quote", ""),
                    "score": c.get("score", 0),
                    "summary": "",
                    "page_number": c.get("page_start"),
                    "chunk_id": c.get("chunk_id", ""),
                    "chunk_text": c.get("quote", ""),
                    "bboxes": c.get("bboxes", []),
                }
                for c in result.get("citations", [])
            ],
        }
        return JSONResponse(content=formatted_result)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/queries/")
async def run_queries(
    doc_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
    retriever: Retriever = Depends(get_retriever),
):
    """Run a predefined set of questions against a document."""
    try:
        question_service = QuestionService(db, retriever)
        result = await question_service.run_predefined_queries(document_id=doc_id)
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
