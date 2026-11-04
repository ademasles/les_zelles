# Architecture

les_zelles is a modular monolith: one Python package, one process, no queue or vector database to operate. Every stage is a plain function or class with a typed interface, so it can be tested alone and replaced later (a Postgres database, a worker pool, Neo4j) without touching the business logic.

## Pipeline

`zelles.pipeline.analyze(data, filename, ...)` runs these stages and reports progress after each one.

1. **Parse** (`ingest/parsers.py`). The media type is sniffed from the bytes, not trusted from the extension. PDFs go through pypdfium2, which gives text lines with bounding boxes (needed for highlights) and has a permissive licence. Pages with no text layer are OCR'd with Tesseract (`fra`). DOCX files are converted to PDF with LibreOffice when it is installed, so they also get pages and boxes; otherwise python-docx keeps the heading styles and tables but no pages. Docling is an optional parser for complex layouts.
2. **Outline and chunk** (`ingest/outline.py`, `ingest/chunking.py`). CCTPs are structured by lots and numbered articles (`LOT 05 MENUISERIES EXTERIEURES`, `3.2.1 Vitrages`). The heading detector recognises those patterns (and avoids false positives like `4 mm` or `1,3 W/m².K`), and chunks follow the outline: each chunk carries its `section_path`, `lot` and `article`, and never mixes two articles. The scope of a requirement ("Logements", "Hall") comes from there.
3. **Index** (`retrieval/`). A French BM25 (accent folding, light stemming) is always on. With an embedding model, dense vectors are added and both rankings are fused with reciprocal rank fusion. The index is per document and in memory; vectors are saved next to the document.
4. **Rules** (`extraction/rules.py`). Regular expressions written for CCTP wording extract the frequent fields with their exact sentence as quote. They are free, deterministic and usually right, so they run first and also serve as hints for the LLM.
5. **LLM extraction** (`extraction/llm_extractor.py`). Fields are split into five groups (materials, glazing and thermal, performance, equipment, compliance). For each group the model receives the relevant passages (the whole document when it fits in about 24k characters, so the provider can cache it) and returns JSON validated against a Pydantic schema. Invalid JSON gets one repair round-trip.
6. **Verify** (`extraction/verify.py`). Every quote must be found in its passage (exact, then fuzzy at 0.88 or more), numeric values must appear in the quote, and domain validators check ranges and formats. The result is a status: `verified`, `unverified` or `invalid`.
7. **Merge** (`extraction/merge.py`). Rules and LLM results are deduplicated per field, value and scope. Agreement between the two raises confidence.
8. **Graph and insights** (`graph/`, `insights.py`). See [agent-and-graph.md](agent-and-graph.md).

## Serving

- `api/app.py`: FastAPI under `/api/v1`. Uploads return `202` with a job id; progress streams over Server-Sent Events. Re-uploading the same file returns the cached analysis, because the document id is the first 16 hex characters of its SHA-256.
- `jobs/runner.py`: an asyncio job manager inside the API process, with bounded concurrency. Jobs left running by a crash are marked failed at startup.
- `storage/`: SQLAlchemy 2 models for documents, jobs and feedback, Alembic migrations applied at startup, and a file workspace (`data/<document_id>/`) for the original, the PDF rendition, chunks and the spec sheet. Document ids are validated against `^[0-9a-f]{16}$` before any path is built.
- `web/static/`: a dependency-free UI served by the same app.

## Scaling path

| Need | Change |
|---|---|
| Several API replicas | `ZELLES_DATABASE_URL` to Postgres; move `data/` to a shared volume or object storage |
| Many documents in parallel | Replace `JobManager` with a worker queue (arq, Celery); the job interface stays the same |
| Cross-document search | Persist chunks and vectors in Postgres with pgvector |
| Cross-document graph | Load `graph?fmt=cypher` exports into Neo4j |

## Design choices

- **No framework for the LLM layer.** The `LLM` protocol is 3 methods; adapters are short and the behaviour (structured output, retries, repair, cost) is explicit and tested.
- **Verification over trust.** A model can be wrong; a quote that is not in the document is caught. This is what makes small local models usable.
- **Deterministic first.** Rules give a free baseline and a regression net; the LLM adds recall.
