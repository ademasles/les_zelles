"""Legacy routes for backward compatibility."""

from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from compat import compat_save_project

router = APIRouter(tags=["legacy"])


@router.post("/save/", deprecated=True)
def save_project(doc_id: str = Form(...), name: str = Form(...), results: str = Form(...)):
    result = compat_save_project(doc_id, name, results)
    if "Deja" in result.get("message", ""):
        return JSONResponse(status_code=409, content=result)
    return JSONResponse(content=result)
