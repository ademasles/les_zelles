"""Question and Answer repositories."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.answer import Answer, AnswerCitation
from app.models.question import Question


class QuestionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self, project_id: str, question_text: str, document_id: str | None = None
    ) -> Question:
        q = Question(
            project_id=project_id,
            document_id=document_id,
            question_text=question_text,
        )
        self.session.add(q)
        await self.session.flush()
        return q

    async def get(self, question_id: str) -> Question | None:
        result = await self.session.execute(
            select(Question).where(Question.id == question_id)
        )
        return result.scalar_one_or_none()

    async def get_by_project(self, project_id: str) -> list[Question]:
        result = await self.session.execute(
            select(Question)
            .where(Question.project_id == project_id)
            .order_by(Question.created_at.desc())
        )
        return list(result.scalars().all())


class AnswerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_answer_with_citations(
        self,
        question_id: str,
        answer_text: str | None,
        model_name: str | None = None,
        prompt_version: str | None = None,
        evidence_quality: str | None = None,
        latency_ms: int | None = None,
        citations: list[dict] | None = None,
    ) -> Answer:
        ans = Answer(
            question_id=question_id,
            answer_text=answer_text,
            model_name=model_name,
            prompt_version=prompt_version,
            evidence_quality=evidence_quality,
            latency_ms=latency_ms,
        )
        self.session.add(ans)
        await self.session.flush()

        if citations:
            for cit in citations:
                citation = AnswerCitation(
                    answer_id=ans.id,
                    chunk_id=cit.get("chunk_id"),
                    page_start=cit.get("page_start"),
                    page_end=cit.get("page_end"),
                    section_title=cit.get("section_title"),
                    quote=cit.get("quote"),
                    score=cit.get("score"),
                )
                self.session.add(citation)

        await self.session.flush()
        return ans

    async def get_by_question(self, question_id: str) -> list[Answer]:
        result = await self.session.execute(
            select(Answer)
            .where(Answer.question_id == question_id)
            .order_by(Answer.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_citations(self, answer_id: str) -> list[AnswerCitation]:
        result = await self.session.execute(
            select(AnswerCitation).where(AnswerCitation.answer_id == answer_id)
        )
        return list(result.scalars().all())
