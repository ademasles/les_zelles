"""Thin application entrypoint.

Routes are thin — they validate input, call compat/service functions, return responses.
No parsing, chunking, embedding, LLM, or database logic here.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.config import settings
from app.core.security import is_allowed_extension, validate_upload_size
from compat import (
    compat_query,
    compat_run_queries,
    compat_save_project,
    compat_store_feedback,
    compat_summary,
    compat_upload,
    documents,
)
from utils.highlight import highlight_chunk

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/upload/")
async def upload_file(file: UploadFile = File(...), doc_id: str = Form(...)):
    if doc_id in documents:
        raise HTTPException(status_code=400, detail="Document ID already exists")
    if not is_allowed_extension(file.filename or ""):
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are accepted")

    content = await file.read()
    validate_upload_size(content)

    suffix = Path(file.filename or "upload.pdf").suffix
    with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        result = await compat_upload(tmp_path, doc_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur traitement document: {e}") from e
    finally:
        tmp_path.unlink(missing_ok=True)


@app.post("/query/")
async def query(doc_id: str = Form(...), question: str = Form(...)):
    try:
        result = await compat_query(doc_id, question)
        if "error" in result:
            return JSONResponse(status_code=404, content=result)
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/queries/")
async def run_queries(doc_id: str = Form(...)):
    try:
        result = await compat_run_queries(doc_id)
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/summary/")
async def summary(doc_id: str):
    result = await compat_summary(doc_id)
    if "error" in result:
        return JSONResponse(status_code=404, content=result)
    return JSONResponse(content=result)


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


@app.get("/highlight/")
def highlight(doc_id: str, chunk_id: int):
    return highlight_chunk(doc_id, chunk_id, documents)


@app.get("/ping/")
def ping():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
