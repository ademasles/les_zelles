"""ProcessingJob repository."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.processing_job import ProcessingJob


class ProcessingJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, document_id: str) -> ProcessingJob:
        job = ProcessingJob(document_id=document_id, status="queued")
        self.session.add(job)
        await self.session.flush()
        return job

    async def get(self, job_id: str) -> ProcessingJob | None:
        result = await self.session.execute(select(ProcessingJob).where(ProcessingJob.id == job_id))
        return result.scalar_one_or_none()

    async def get_by_document(self, document_id: str) -> list[ProcessingJob]:
        result = await self.session.execute(
            select(ProcessingJob)
            .where(ProcessingJob.document_id == document_id)
            .order_by(ProcessingJob.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_status(
        self,
        job_id: str,
        status: str,
        current_step: str | None = None,
        error_message: str | None = None,
    ) -> ProcessingJob | None:
        job = await self.get(job_id)
        if job is None:
            return None
        job.status = status
        if current_step is not None:
            job.current_step = current_step
        if error_message is not None:
            job.error_message = error_message
        if status in ("completed", "failed"):
            job.completed_at = datetime.now(UTC)
        await self.session.flush()
        return job
