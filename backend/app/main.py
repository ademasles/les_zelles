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
    setup_logging(debug=settings.debug)
    from database.database import init_legacy_tables

    init_legacy_tables()
    await init_db()
    yield


def create_app() -> FastAPI:
    import main as legacy_main

    app = legacy_main.app
    app.router.lifespan_context = lifespan

    if not any(getattr(route, "path", None) == "/api/health" for route in app.routes):
        app.add_api_route("/api/health", health_check, methods=["GET"], tags=["health"])

    app.include_router(summaries_router)
    app.include_router(projects_router)
    app.include_router(project_queries_router)

    app.title = settings.app_title
    return app


app = create_app()
