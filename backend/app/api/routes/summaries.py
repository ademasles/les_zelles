"""Summaries route module, now using the new service layer."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.services.document_service import DocumentService

router = APIRouter(tags=["summaries"])


@router.get("/summary/{doc_id}")
async def get_summary(doc_id: str, db: AsyncSession = Depends(get_db)):
    """Generate and retrieve a summary for a document."""
    try:
        doc_service = DocumentService(db)
        summary_text = await doc_service.generate_and_save_summary(doc_id)
        return JSONResponse(
            content={
                "doc_id": doc_id,
                "summary": summary_text,
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summarization failed: {str(e)}") from e
