"""Uploads route module."""

from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_retriever
from app.core.security import is_allowed_extension, validate_upload_size
from app.database.session import get_db
from app.rag.retriever import Retriever
from app.repositories.document_repository import DocumentRepository
from app.repositories.project_repository import ProjectRepository
from app.services.processing_service import process_document

router = APIRouter(tags=["upload"])


@router.post("/upload/")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    doc_id: str = Form(...),  # Using doc_id as project_id for now
    db: AsyncSession = Depends(get_db),
    retriever: Retriever = Depends(get_retriever),
):
    """
    Accepts a document upload, creates project/document entries,
    and schedules background processing. Returns immediately.
    """
    if not is_allowed_extension(file.filename or ""):
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are accepted")

    content = await file.read()
    validate_upload_size(content)

    project_id = doc_id  # Use the provided doc_id as the project_id
    filename = file.filename or "upload"

    # Save content to a temporary file
    suffix = Path(filename).suffix
    with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        # Clear any previous data for this project/document
        retriever.vector_store.delete_document(document_id=project_id)

        # Create project and document records in the database
        project_repo = ProjectRepository(db)
        doc_repo = DocumentRepository(db)

        await project_repo.create_or_update(project_id, filename)
        document = await doc_repo.create(
            project_id=project_id,
            filename=filename,
            storage_path=str(tmp_path),
        )

        # Schedule the processing in the background
        background_tasks.add_task(
            process_document,
            document_id=document.id,
            project_id=project_id,
            file_path=tmp_path,
            filename=filename,
        )

        return JSONResponse(
            status_code=202,
            content={
                "message": "File upload accepted. Processing in background.",
                "project_id": project_id,
                "document_id": document.id,
            },
        )
    except Exception as e:
        # Ensure temp file is cleaned up on error
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Erreur traitement document: {e}") from e
