"""API route for storing user feedback."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.repositories.feedback_repository import FeedbackRepository

router = APIRouter(tags=["feedback"])


class FeedbackEntry(BaseModel):
    question: str
    response: str
    score: float


@router.post("/feedback/")
async def store_feedback(entry: FeedbackEntry, db: AsyncSession = Depends(get_db)):
    """Stores a new feedback entry."""
    feedback_repo = FeedbackRepository(db)
    await feedback_repo.create(question=entry.question, response=entry.response, score=entry.score)
    return {"status": "ok"}
