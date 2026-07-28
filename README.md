# Analyse IA d’Appels d’Offres (CCTP) – Analyse-DCE

This project provides a comprehensive application for the intelligent analysis of tender documents (CCTP in French). It allows users to upload documents, extract information, and perform semantic question-answering through a web interface.

---

## Architecture Overview

The project follows a modern, decoupled architecture with a FastAPI backend and a Streamlit frontend.

-   **Backend**: A Python backend built with FastAPI, following clean architecture principles. It handles all business logic, including document processing, RAG pipeline execution, and database interactions.
-   **Frontend**: A Streamlit web application that serves as the user interface. It is a pure client that interacts with the backend via a REST API.
-   **LLM Service**: An Ollama container that serves the `gemma4:e4b` model for generative tasks.
-   **Database**: A PostgreSQL database (managed via Docker) for persisting project and analysis data.

### Backend Architecture

The backend code is organized into a modular and scalable structure within the `backend/` directory, following clean architecture principles:

```
backend/
├── alembic/              # Alembic database migrations
├── app/                  # Main application source code
│   ├── api/              # FastAPI routers and input schemas
│   │   └── routes/       # API endpoint definitions (documents, projects, etc.)
│   ├── core/             # Core services: config, logging, security
│   ├── database/         # SQLAlchemy session management and base models
│   ├── llm/              # LLM client abstractions (e.g., Ollama)
│   ├── models/           # SQLAlchemy ORM models
│   ├── preprocessing/    # Document processing pipeline
│   │   ├── parsers/      # Document parsers (PDF, DOCX, OCR)
│   │   └── markdown/     # Markdown cleaning and splitting
│   ├── rag/              # RAG pipeline components
│   │   ├── embeddings.py # Embedding generation
│   │   ├── prompts.py    # Prompt templates
│   │   ├── retriever.py  # FAISS-based retriever
│   │   └── vector_store.py # Vector store abstraction
│   ├── repositories/     # Data access layer (CRUD operations for each model)
│   └── services/         # Business logic orchestration (processing, RAG)
├── alembic.ini           # Alembic configuration
├── Dockerfile            # Container definition for the backend
├── Makefile              # Development commands for linting, testing, running, etc.
├── pyproject.toml        # Project metadata and dependencies (for uv)
└── tests/                # Pytest tests (unit, integration, golden)
```

## Getting Started

### Prerequisites

-   Python 3.11+
-   [uv](https://github.com/astral-sh/uv) (recommended for Python dependency management)
-   Docker and Docker Compose
-   System tools for OCR and document conversion:
    ```bash
    # On Debian/Ubuntu
    sudo apt-get update && sudo apt-get install -y libreoffice tesseract-ocr
    ```

### Environment Configuration

Copy the example `.env.example` file to a new `.env` file and customize the variables if needed. This file is ignored by Git.

```bash
cp .env.example .env
```

### 1. Running with Docker (Recommended)

The simplest way to run the entire application stack is with Docker Compose.

-   **Build and launch all services (Backend, Frontend, DB):**
    ```bash
    docker-compose up --build
    ```

-   **Launch with the local LLM service (Ollama):**
    To include the local Ollama service for the RAG pipeline, use the `ollama` profile.
    ```bash
    docker-compose --profile ollama up --build
    ```
    *Note: The first time you run this, it will download the LLM model (`gemma4:e4b`), which may take some time.*

### 2. Local Development

For development, you can run the services manually. The `backend/Makefile` provides convenient shortcuts for most tasks.

1.  **Install Dependencies:**
    - **Backend:**
      ```bash
      cd backend
      uv pip sync pyproject.toml --all-extras
      cd ..
      ```
    - **Frontend:**
      ```bash
      uv pip install -r frontend/requirements.txt
      ```

2.  **Run Database Migrations:**
    From the `backend/` directory:
    ```bash
    make alembic-upgrade
    ```

3.  **Run the Development Servers:**
    - **Backend (FastAPI):**
      From the `backend/` directory:
      ```bash
      make run
      ```
    - **Frontend (Streamlit):**
      From the project root directory:
      ```bash
      streamlit run frontend/app.py
      ```

4.  **Code Quality & Testing:**
    From the `backend/` directory, you can use the Makefile to run checks:
    ```bash
    # Run all checks (lint, format, types, tests)
    make check

    # Run only tests
    make test

    # Auto-format the code
    make format
    ```

## Key Technologies

-   **Backend**: Python, FastAPI, SQLAlchemy, Alembic, `sentence-transformers`, FAISS, PyMuPDF, Tesseract
-   **Frontend**: Streamlit
-   **LLM**: Ollama (`gemma4:e4b`)
-   **Database**: PostgreSQL
-   **DevOps**: Docker, pre-commit, Ruff, MyPy

## Project Conventions

-   **Code Quality**: We use `ruff` for linting/formatting and `mypy` for type checking. These are enforced via `pre-commit` hooks.
-   **Dependency Management**: Backend dependencies are managed with `uv` via `pyproject.toml`.
-   **Testing**: Tests are written with `pytest` and are located in the `backend/tests/` directory.

## Contact

-   **Author**: Anton Demasles
-   **Email**: demaslesa@gmail.com
