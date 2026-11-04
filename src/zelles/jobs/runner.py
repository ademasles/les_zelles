"""Background analysis jobs with live progress events.

The default runner is in-process (asyncio workers): no Redis, no extra
service, which suits one machine with one local model. Job state is persisted
in the database so status survives restarts; a job that was running when the
process stopped is marked failed on startup and can be resubmitted. For
horizontal scale, the same ``submit`` interface can be backed by a queue
(arq, Celery, Cloud Tasks) without touching the API.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy import update

from zelles.config import Settings
from zelles.llm.base import LLM, Embedder
from zelles.pipeline import analyze
from zelles.storage.db import JobRow
from zelles.storage.workspace import Workspace

log = logging.getLogger(__name__)


@dataclass
class _Task:
    job_id: str
    document_id: str
    filename: str
    data: bytes


class JobManager:
    def __init__(
        self,
        settings: Settings,
        workspace: Workspace,
        *,
        llm: LLM | None,
        embedder: Embedder | None,
        workers: int = 1,
    ) -> None:
        self.settings, self.workspace = settings, workspace
        self.llm, self.embedder = llm, embedder
        self.queue: asyncio.Queue[_Task] = asyncio.Queue()
        self.listeners: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)
        self.workers = workers
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        with self.workspace.sessions.begin() as session:
            session.execute(
                update(JobRow)
                .where(JobRow.status.in_(["queued", "running"]))
                .values(status="failed", error="interrupted by a restart")
            )
        self._tasks = [asyncio.create_task(self._worker()) for _ in range(self.workers)]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    def submit(self, document_id: str, filename: str, data: bytes) -> str:
        job_id = uuid.uuid4().hex
        with self.workspace.sessions.begin() as session:
            session.add(
                JobRow(
                    id=job_id,
                    document_id=document_id,
                    status="queued",
                    stage="queued",
                    message="Queued",
                )
            )
        self.queue.put_nowait(_Task(job_id, document_id, filename, data))
        return job_id

    def status(self, job_id: str) -> dict[str, Any] | None:
        with self.workspace.sessions() as session:
            row = session.get(JobRow, job_id)
            if row is None:
                return None
            return {
                "job_id": row.id,
                "document_id": row.document_id,
                "status": row.status,
                "stage": row.stage,
                "progress": row.progress,
                "message": row.message,
                "error": row.error,
            }

    def subscribe(self, job_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.listeners[job_id].append(queue)
        return queue

    def unsubscribe(self, job_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        if queue in self.listeners.get(job_id, []):
            self.listeners[job_id].remove(queue)

    async def _emit(self, job_id: str, **fields: Any) -> None:
        with self.workspace.sessions.begin() as session:
            row = session.get(JobRow, job_id)
            if row is not None:
                for key, value in fields.items():
                    if hasattr(row, key):
                        setattr(row, key, value)
        event = {"job_id": job_id, **fields}
        for queue in list(self.listeners.get(job_id, [])):
            queue.put_nowait(event)

    async def _worker(self) -> None:
        while True:
            task = await self.queue.get()
            try:
                await self._run(task)
            finally:
                self.queue.task_done()

    async def _run(self, task: _Task) -> None:
        await self._emit(
            task.job_id, status="running", stage="start", progress=0.0, message="Starting"
        )

        async def progress(stage: str, fraction: float, message: str) -> None:
            await self._emit(task.job_id, stage=stage, progress=round(fraction, 3), message=message)

        try:
            analysis = await analyze(
                task.data,
                task.filename,
                settings=self.settings,
                llm=self.llm,
                embedder=self.embedder,
                progress=progress,
            )
            await asyncio.to_thread(self.workspace.save, analysis)
        except Exception as exc:
            log.exception("job %s failed", task.job_id)
            self.workspace.mark_failed(task.document_id)
            await self._emit(
                task.job_id, status="failed", stage="failed", error=str(exc), message="Failed"
            )
            return
        await self._emit(task.job_id, status="done", stage="done", progress=1.0, message="Done")
