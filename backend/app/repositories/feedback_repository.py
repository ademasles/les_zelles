"""Feedback repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feedback import Feedback


class FeedbackRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        answer_id: str,
        rating: float | None = None,
        comment: str | None = None,
    ) -> Feedback:
        fb = Feedback(answer_id=answer_id, rating=rating, comment=comment)
        self.session.add(fb)
        await self.session.flush()
        return fb

    async def get_by_answer(self, answer_id: str) -> list[Feedback]:
        result = await self.session.execute(select(Feedback).where(Feedback.answer_id == answer_id))
        return list(result.scalars().all())
