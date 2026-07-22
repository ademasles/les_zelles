"""Summaries route module — delegates to in-memory compat layer."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from compat import compat_summary

router = APIRouter(tags=["summaries"])


@router.get("/summary/{doc_id}")
async def get_summary(doc_id: str):
    try:
        result = await compat_summary(doc_id)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return JSONResponse(
            content={
                "doc_id": doc_id,
                "summary": result["summary"],
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summarization failed: {str(e)}") from e
