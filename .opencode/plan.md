## Plan: Centralize backend config

Add one typed Pydantic Settings module, keep defaults aligned with `.env.example`, then replace only low-risk hardcoded config reads in backend modules that already depend on those values. Goal is central source of truth without touching route/business logic beyond import-time constants.

**Steps**
1. Add `backend/app/core/config.py` with `Settings`, `get_settings()`, and module-level `settings`, using `pydantic-settings` and safe local defaults that match `.env.example`.
2. Verify backend packaging already includes `pydantic-settings` and keep dependency list unchanged unless it is missing.
3. Align root `.env.example` with the new settings fields and defaults, including app env, database URL, storage dir, parser, OCR, vector store, embedding model, LLM provider/model, Ollama URL, upload limit, and backend API URL.
4. Replace low-risk direct config literals with `from app.core.config import settings` in backend callers that currently hardcode values: `backend/nlp/qa.py`, `backend/nlp/summarization.py`, `backend/nlp/filtering.py`, `backend/preprocessing/extraction.py`, `backend/database/database.py`, `backend/main.py`, `backend/utils/highlight.py`, `backend/nlp/train_cross_encoder.py`, and `backend/preprocessing/loading.py` where the change stays import-time only.
5. Update `backend/app/main.py` only if useful for app title/debug wiring, but do not move any business logic there.
6. Adjust `docker-compose.yml` only if needed to ensure backend receives the same env names, and keep `.env` external to the image.
7. Update README setup instructions at repo root so they mention copying `.env.example` to `.env` and that Pydantic Settings loads backend config.

**Relevant files**
- `/Users/ademasles/Developer/Personal/les_zelles/backend/app/core/config.py` — new typed settings source
- `/Users/ademasles/Developer/Personal/les_zelles/backend/pyproject.toml` — confirm `pydantic-settings`
- `/Users/ademasles/Developer/Personal/les_zelles/.env.example` — safe defaults for local dev
- `/Users/ademasles/Developer/Personal/les_zelles/backend/main.py` — legacy app constants like feedback file and training threshold
- `/Users/ademasles/Developer/Personal/les_zelles/backend/database/database.py` — SQLite URL default
- `/Users/ademasles/Developer/Personal/les_zelles/backend/nlp/qa.py` — Ollama URL and model defaults
- `/Users/ademasles/Developer/Personal/les_zelles/backend/nlp/summarization.py` — Ollama URL and model defaults
- `/Users/ademasles/Developer/Personal/les_zelles/backend/nlp/filtering.py` — embedding model name
- `/Users/ademasles/Developer/Personal/les_zelles/backend/preprocessing/extraction.py` — OCR language
- `/Users/ademasles/Developer/Personal/les_zelles/backend/preprocessing/chunking.py` — chunk size default
- `/Users/ademasles/Developer/Personal/les_zelles/backend/preprocessing/loading.py` — queries file path
- `/Users/ademasles/Developer/Personal/les_zelles/backend/nlp/train_cross_encoder.py` — feedback/model output paths
- `/Users/ademasles/Developer/Personal/les_zelles/backend/utils/highlight.py` — storage path usage
- `/Users/ademasles/Developer/Personal/les_zelles/docker-compose.yml` — backend env wiring
- `/Users/ademasles/Developer/Personal/les_zelles/README.md` — setup instructions

**Verification**
1. Run `python -m pip install -e ".[dev]"` from `backend/`.
2. Run `python -c "from app.core.config import settings; print(settings.app_env); print(settings.storage_dir)"` from `backend/`.
3. Run `pytest` from `backend/`.
4. Run `uvicorn app.main:app --reload` from `backend/` and confirm `GET /api/health` still returns `{"status":"ok"}`.
5. If `make` is available, run `make test` and `make run` from `backend/`.

**Decisions**
- Keep defaults unchanged wherever possible to avoid behavior drift.
- Do not introduce new config fields for upload limits or broader parser abstractions unless code already uses them.
- Treat `DATABASE_URL`, storage paths, model IDs, and OCR language as centralization targets, but change only the callers that can safely consume `settings` without a deeper refactor.

**Further Considerations**
1. Should `backend/database/database.py` read the same `DATABASE_URL` as the rest of backend, or keep its current `projects.db` default until the DB refactor ticket? Recommendation: align now only if the app already expects `analyse_dce.db`; otherwise preserve current DB behavior and leave a TODO.
2. Should `max_upload_mb` be added even though no current upload limit exists? Recommendation: include it in settings and `.env.example` for future use, but do not wire enforcement in this ticket.
3. Should README mention root `.env.example` explicitly rather than a backend-local one? Recommendation: yes, because the file lives at repo root, not under `backend/`.
