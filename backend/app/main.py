"""Packaged backend entrypoint for Analyse-DCE.

This keeps the legacy top-level FastAPI app alive while exposing the new
package import path expected by later refactor tickets.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI

from app.api.routes.health import health_check
from app.core.config import settings

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import main as legacy_main


def create_app() -> FastAPI:
    app = legacy_main.app

    if not any(getattr(route, "path", None) == "/api/health" for route in app.routes):
        app.add_api_route("/api/health", health_check, methods=["GET"], tags=["health"])

    app.title = "Analyse-DCE API"
    return app


app = create_app()
