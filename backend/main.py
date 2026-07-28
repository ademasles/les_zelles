"""Thin application entrypoint.

Routes are thin — they validate input, call compat/service functions, return responses.
No parsing, chunking, embedding, LLM, or database logic here.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

import uvicorn
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import is_allowed_extension, validate_upload_size
from app.database.session import get_db
from app.rag.retriever import Retriever
from app.api.dependencies import get_retriever
from app.repositories.document_repository import DocumentRepository
from app.repositories.project_repository import ProjectRepository
from app.services.document_service import DocumentService
from app.services.processing_service import process_document
from app.services.question_service import QuestionService
from compat import (
    compat_save_project,
    compat_store_feedback,
)
from utils.highlight import highlight_chunk

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/save/")
async def save_project(doc_id: str = Form(...), name: str = Form(...), results: str = Form(...)):
    result = compat_save_project(doc_id, name, results)
    if "Deja" in result.get("message", ""):
        return JSONResponse(status_code=409, content=result)
    return JSONResponse(content=result)


class FeedbackEntry(BaseModel):
    question: str
    response: str
    score: float


@app.post("/feedback/")
def store_feedback(entry: FeedbackEntry):
    return compat_store_feedback(entry.question, entry.response, entry.score)


@app.post("/train/")
def trigger_training():
    feedback_file = settings.feedback_file
    if not feedback_file.exists():
        return {"status": "no_feedback_file"}
    with open(feedback_file, encoding="utf-8") as f:
        feedback_count = sum(1 for _ in f)
    if feedback_count < settings.train_threshold:
        return {"status": "not_enough_feedback", "count": feedback_count}
    import subprocess

    try:
        subprocess.run(["python3", "train_cross_encoder.py"], check=True)
        return {"status": "training_started", "feedback_used": feedback_count}
    except subprocess.CalledProcessError as e:
        return {"status": "error", "message": str(e)}


# @app.get("/highlight/")
# def highlight(doc_id: str, chunk_id: int):
#     return highlight_chunk(doc_id, chunk_id, documents)


@app.get("/ping/")
def ping():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
