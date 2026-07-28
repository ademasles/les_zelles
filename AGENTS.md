# AGENTS.md

## Mission
Analyse-DCE = FastAPI + Streamlit RAG POC for CCTP/tender analysis.

Goal:
PDF/DOCX -> Parse -> Chunk -> Retrieve -> Answer -> Cite.

## Read First
- REFRACTOR_DECISIONS.md
- AGENTS.md
- app/main.py
- core/config.py
- pyproject.toml

## Architecture
Routes -> Services -> Repositories
                     -> Parser
                     -> Retriever
                     -> VectorStore
                     -> LLMClient

### Routes
DO:
- validate
- call services
- return schemas

DON'T:
- parse
- OCR
- chunk
- embed
- call LLM
- query DB directly

### Services
Own workflows.
Examples:
- DocumentService
- ProcessingService
- RAGService

### Repositories
Own SQL persistence.
No business logic.

### Parser
DocumentParser

Order:
Docling -> PyMuPDF -> Tesseract

### Vector Store
Use VectorStore abstraction.
Current: FAISS.

### LLM
Use LLMClient abstraction.
Current: Ollama (`gemma4:e4b`).

## RAG Rules
Docling Markdown -> chunking/RAG.
Structured output -> provenance/citations/highlighting.

Chunks keep:
- document_id
- section_title
- heading_path
- page info
- source metadata

Answers:
- evidence first
- citations required
- if no evidence, say so

## Database
Current:
- SQLite

Future:
- PostgreSQL + pgvector

Do not migrate unless explicitly requested.

## Storage
SQL:
- projects
- documents
- jobs
- chunks
- answers
- citations

Files:
- raw docs
- markdown
- parsed JSON

Vector:
- embeddings/indexes

## Frontend
Streamlit may:
- upload
- ask
- summarize
- show citations

Streamlit must NOT:
- parse
- embed
- call LLM directly
- access DB directly

## Security
Uploads are untrusted.

Must have:
- PDF/DOCX only
- size limits
- path traversal protection
- prompt injection protection
- no raw document logging

## Dependency Rules
Backend source of truth:
- pyproject.toml

Prefer:
pip install -e ".[dev]"

## Testing
No live LLM in CI.
Mock:
- LLM
- parser
- embeddings

Prefer:
- unit tests
- integration tests
- golden extraction tests

## Refactor Discipline
For every ticket:
1. Read ticket
2. Inspect code
3. Make minimal change
4. Add/update tests
5. Run checks
6. Avoid unrelated cleanup

No big-bang rewrites.

## Validation
Run these checks from the `backend/` directory before committing:
```bash
ruff check . && ruff format --check . && mypy app && pytest
```
To run the web server for manual testing:
```bash
uvicorn app.main:app --reload
```

## Roadmap
T2 Storage/DB
T3 Parsing
T4 RAG
T5 Jobs
T6 Frontend
T7 Security
T8 Testing/CI
T9 Docker
T10 Alembic + ADRs

## Priority Order
1. User request
2. REFRACTOR_DECISIONS.md
3. AGENTS.md
4. Tests
5. Convenience

