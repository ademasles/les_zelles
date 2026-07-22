"""Summaries route module.

Wraps legacy summarization endpoints from nlp.summarization.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(tags=["summaries"])


@router.get("/summary/{doc_id}")
async def get_summary(doc_id: str):
    """Get summary for a document.

    Wraps legacy: GET /summary/{doc_id} → summarize_global()
    """
    # Import legacy function at call time to avoid circular imports
    from core.config import settings
    from db.database import SessionLocal
    from sqlalchemy import text

    from nlp.summarization import summarize_global

    try:
        # Get project ID from the filename
        with SessionLocal() as db:
            result = db.execute(
                text("SELECT project_id FROM documents WHERE filename = :filename"),
                {"filename": doc_id},
            )
            row = result.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
            project_id = row[0]

            # Get all document markdown content for the project
            result = db.execute(
                text("SELECT markdown_content FROM documents WHERE project_id = :project_id"),
                {"project_id": project_id},
            )
            project_docs = result.fetchall()

        if not project_docs:
            raise HTTPException(status_code=404, detail="No documents found for project")

        all_summaries = " ".join([doc[0] for doc in project_docs if doc[0]])
        summary = summarize_global(all_summaries, model=settings.llm_model)

        return JSONResponse(
            content={
                "doc_id": doc_id,
                "project_id": project_id,
                "summary": summary,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summarization failed: {str(e)}")
