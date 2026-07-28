"""Packaged backend entrypoint for Analyse-DCE.

Calls init_db() on startup to ensure all tables exist.
Initializes logging and shared singletons on startup.
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api.routes.health import health_check
from app.api.routes.project_queries import router as project_queries_router
from app.api.routes.projects import router as projects_router
from app.api.routes.summaries import router as summaries_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.database.session import init_db

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup logging
    setup_logging(debug=settings.debug)

    # Initialize database tables
    from database.database import init_legacy_tables
    init_legacy_tables()
    await init_db()

    # Initialize and attach stateful services (singletons)
    from app.rag.embeddings import EmbeddingService
    from app.rag.retriever import Retriever
    from app.rag.vector_store import FaissVectorStore

    embedding_service = EmbeddingService()
    vector_store = FaissVectorStore()
    # TODO: Load from disk if it exists
    app.state.retriever = Retriever(embedding_service, vector_store)

    yield

    # Teardown can happen here if needed, e.g., saving the vector store to disk



def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_title, lifespan=lifespan)

    # IMPORTANT: Import and include routers here to avoid circular imports
    from fastapi import Form
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse

    from app.api.routes.feedback import router as feedback_router
    from app.api.routes.uploads import router as uploads_router
    from app.repositories.project_repository import ProjectRepository

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # New, refactored routers
    app.include_router(uploads_router)
    app.include_router(summaries_router, prefix="/api")
    app.include_router(projects_router, prefix="/api")
    app.include_router(project_queries_router, prefix="/api")
    app.include_router(feedback_router, prefix="/api")
    app.add_api_route("/api/health", health_check, methods=["GET"], tags=["health"])

    # TODO: Move these legacy routes to their own routers
    @app.post("/save/")
    async def save_project(doc_id: str = Form(...), name: str = Form(...), results: str = Form(...)):
        result = ProjectRepository.save_legacy_project(doc_id, name, results)
        if "Deja" in result.get("message", ""):
            return JSONResponse(status_code=409, content=result)
        return JSONResponse(content=result)

    @app.post("/train/")
    def trigger_training():
        feedback_file = settings.feedback_file
        if not feedback_file.exists():
            return {"status": "no_feedback_file"}
        with open(feedback_file, encoding="utf-8") as f:
            feedback_count = sum(1 for _ in f)
        if feedback_count < settings.train_threshold:
            return {"status": "not_enough_feedback", "count": feedback_count}
        import subprocess

        try:
            subprocess.run(["python3", "train_cross_encoder.py"], check=True)
            return {"status": "training_started", "feedback_used": feedback_count}
        except subprocess.CalledProcessError as e:
            return {"status": "error", "message": str(e)}

    @app.get("/ping/")
    def ping():
        return {"status": "ok"}

    return app


app = create_app()
