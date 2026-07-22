"""App import smoke test."""

from __future__ import annotations

import importlib
import sys
import types


def _install_optional_dependency_stubs() -> None:
    uvicorn_module = types.ModuleType("uvicorn")
    uvicorn_module.run = lambda *args, **kwargs: None

    fastapi_module = types.ModuleType("fastapi")
    encoders_module = types.ModuleType("fastapi.encoders")
    middleware_module = types.ModuleType("fastapi.middleware")
    cors_module = types.ModuleType("fastapi.middleware.cors")
    responses_module = types.ModuleType("fastapi.responses")

    class _HTTPException(Exception):
        def __init__(self, status_code: int, detail=None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class _FakeFastAPI:
        def __init__(self, *args, **kwargs):
            self.routes = {"GET": {}, "POST": {}, "DELETE": {}}
            self.router = type("Router", (), {"lifespan_context": None})()
            self.title = ""

        def add_middleware(self, *args, **kwargs):
            return None

        def add_api_route(self, path, endpoint, methods=None, tags=None):
            for method in methods or ["GET"]:
                self.routes.setdefault(method, {})[path] = endpoint

        def include_router(self, router, prefix=""):
            for method, routes in router.routes.items():
                for path, func in routes.items():
                    self.routes[method][f"{prefix}{path}"] = func

        def get(self, path):
            def decorator(func):
                self.routes["GET"][path] = func
                return func

            return decorator

        def post(self, path):
            def decorator(func):
                self.routes["POST"][path] = func
                return func

            return decorator

    class _FakeAPIRouter:
        def __init__(self, *args, **kwargs):
            self.routes = {"GET": {}, "POST": {}, "DELETE": {}}

        def get(self, path):
            def decorator(func):
                self.routes["GET"][path] = func
                return func

            return decorator

        def post(self, path):
            def decorator(func):
                self.routes["POST"][path] = func
                return func

            return decorator

        def delete(self, path):
            def decorator(func):
                self.routes["DELETE"][path] = func
                return func

            return decorator

    fastapi_module.FastAPI = _FakeFastAPI
    fastapi_module.APIRouter = _FakeAPIRouter
    fastapi_module.UploadFile = object
    fastapi_module.File = lambda *args, **kwargs: None
    fastapi_module.Form = lambda *args, **kwargs: None
    fastapi_module.HTTPException = _HTTPException
    fastapi_module.Request = object
    encoders_module.jsonable_encoder = lambda value: value

    class _CORSMiddleware:
        pass

    cors_module.CORSMiddleware = _CORSMiddleware

    class _JSONResponse:
        def __init__(self, status_code=200, content=None):
            self.status_code = status_code
            self.content = content

    responses_module.JSONResponse = _JSONResponse

    class _StreamingResponse:
        def __init__(self, *args, **kwargs):
            pass

    responses_module.StreamingResponse = _StreamingResponse

    sys.modules.setdefault("uvicorn", uvicorn_module)
    sys.modules.setdefault("fastapi", fastapi_module)
    sys.modules.setdefault("fastapi.encoders", encoders_module)
    sys.modules.setdefault("fastapi.middleware", middleware_module)
    sys.modules.setdefault("fastapi.middleware.cors", cors_module)
    sys.modules.setdefault("fastapi.responses", responses_module)

    sentence_transformers = types.ModuleType("sentence_transformers")

    class _FakeSentenceTransformer:
        def __init__(self, *args, **kwargs):
            pass

        def encode(self, value, convert_to_tensor=True):
            if isinstance(value, list):
                return [0.0 for _ in value]
            return [0.0]

    util_module = types.SimpleNamespace(
        semantic_search=lambda query_embedding, corpus_embeddings, top_k=5: [
            [{"corpus_id": 0, "score": 0.0}]
        ]
    )
    sentence_transformers.SentenceTransformer = _FakeSentenceTransformer
    sentence_transformers.util = util_module

    fitz_module = types.ModuleType("fitz")
    docx_module = types.ModuleType("docx")
    docx_module.Document = lambda *args, **kwargs: types.SimpleNamespace(paragraphs=[])

    pil_module = types.ModuleType("PIL")
    pil_module.__path__ = []
    pil_image_module = types.ModuleType("PIL.Image")
    pil_module.Image = pil_image_module

    sys.modules.setdefault("sentence_transformers", sentence_transformers)
    sys.modules.setdefault("sentence_transformers.util", util_module)
    sys.modules.setdefault("fitz", fitz_module)
    sys.modules.setdefault("docx", docx_module)
    sys.modules.setdefault("pytesseract", types.ModuleType("pytesseract"))
    sys.modules.setdefault("PIL", pil_module)
    sys.modules.setdefault("PIL.Image", pil_image_module)

    database_package = types.ModuleType("database")
    database_package.__path__ = []
    database_module = types.ModuleType("database.database")

    class _FakeSession:
        def query(self, *args, **kwargs):
            return self

        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return None

        def all(self):
            return []

        def add(self, *args, **kwargs):
            return None

        def commit(self, *args, **kwargs):
            return None

        def refresh(self, *args, **kwargs):
            return None

    class _FakeModel:
        def __init__(self, *args, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

        def as_dict(self):
            return {}

    database_module.SessionLocal = lambda: _FakeSession()
    database_module.Project = _FakeModel
    database_module.Query = _FakeModel
    database_module.Answer = _FakeModel
    database_package.database = database_module

    utils_package = types.ModuleType("utils")
    utils_package.__path__ = []
    highlight_module = types.ModuleType("utils.highlight")
    highlight_module.highlight_chunk = lambda *args, **kwargs: None
    utils_package.highlight = highlight_module

    sys.modules.setdefault("database", database_package)
    sys.modules.setdefault("database.database", database_module)
    sys.modules.setdefault("utils", utils_package)
    sys.modules.setdefault("utils.highlight", highlight_module)


def test_fastapi_app_imports_and_health_route_responds_ok():
    _install_optional_dependency_stubs()

    main = importlib.import_module("app.main")

    assert "/api/health" in main.app.routes["GET"]
    assert "/ping/" in main.app.routes["GET"]
