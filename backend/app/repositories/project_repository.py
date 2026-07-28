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

    @staticmethod
    def save_legacy_project(doc_id: str, name: str, results_json: str) -> dict[str, str]:
        import json
        from database.database import Answer, Project as LegacyProject, Query, SessionLocal

        results = json.loads(results_json)
        db = SessionLocal()
        try:
            project = db.query(LegacyProject).filter(LegacyProject.id == doc_id).first()
            if not project:
                new_proj = LegacyProject(id=doc_id, name=name)
                db.add(new_proj)
                db.commit()
            else:
                return {"message": "Deja existant"}

            for question_text, result in results.items():
                new_query = Query(
                    project_id=doc_id,
                    question=question_text,
                    best_answer=result.get("best_answer"),
                )
                db.add(new_query)
                db.commit()
                db.refresh(new_query)

                for alt in result.get("alternatives", []):
                    answer = Answer(
                        query_id=new_query.id,
                        response=alt.get("response"),
                        score=alt.get("score"),
                        summary=alt.get("summary"),
                        page_number=alt.get("page_number"),
                        chunk_id=alt.get("chunk_id"),
                        excerpt=alt.get("chunk_text"),
                    )
                    db.add(answer)
                db.commit()

            return {"message": "Projet et questions sauvegardes avec succes"}
        finally:
            db.close()
