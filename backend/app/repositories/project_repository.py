"""Project repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, name: str) -> Project:
        project = Project(name=name)
        self.session.add(project)
        await self.session.flush()
        return project

    async def get(self, project_id: str) -> Project | None:
        result = await self.session.execute(select(Project).where(Project.id == project_id))
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Project]:
        result = await self.session.execute(select(Project).order_by(Project.created_at.desc()))
        return list(result.scalars().all())

    async def delete(self, project_id: str) -> bool:
        project = await self.get(project_id)
        if project is None:
            return False
        await self.session.delete(project)
        await self.session.flush()
        return True
