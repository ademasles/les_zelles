"""Typed application settings, loaded from environment variables and `.env`.

Every setting can be overridden with an environment variable prefixed with
``ZELLES_`` (for example ``ZELLES_LLM_MODEL=ollama:qwen3:8b``).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the API, worker, CLI and MCP server."""

    model_config = SettingsConfigDict(
        env_prefix="ZELLES_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ------------------------------------------------------------------ storage
    data_dir: Path = Field(default=Path("./data"), description="Uploaded files and artifacts.")
    database_url: str = Field(
        default="",
        description="SQLAlchemy URL. Defaults to a SQLite file inside data_dir.",
    )

    # ---------------------------------------------------------------------- LLM
    llm_model: str = Field(
        default="none",
        description=(
            "Model used for extraction and Q&A, as 'provider:model'. "
            "Examples: 'ollama:qwen3:8b', 'llamacpp:local', 'openai:gpt-4.1-mini', "
            "'anthropic:claude-opus-5-5', 'none' (rules-only, no LLM)."
        ),
    )
    llm_base_url: str | None = Field(
        default=None, description="Override the provider's base URL (OpenAI-compatible servers)."
    )
    llm_api_key: SecretStr | None = Field(default=None, description="API key for cloud providers.")
    llm_timeout_s: float | None = Field(
        default=None,
        description="Seconds to wait for one LLM reply. Defaults to 600 for local servers, "
        "180 for cloud APIs.",
    )
    llm_max_retries: int = 2
    llm_concurrency: int = Field(
        default=2, description="Parallel LLM calls. Use 1 for a single local GPU."
    )
    llm_max_output_tokens: int = 4096
    ollama_num_ctx: int = Field(
        default=6144,
        description="Context window requested from Ollama. Its own default is often 4096, "
        "too small for CCTP passages.",
    )
    ollama_think: bool = Field(
        default=False, description="Let Ollama thinking models reason before answering."
    )
    llm_price_input_per_mtok: float | None = Field(
        default=None, description="USD per million input tokens, to override the built-in table."
    )
    llm_price_output_per_mtok: float | None = None

    # ---------------------------------------------------------------- retrieval
    embedding_model: str = Field(
        default="none",
        description=(
            "Embeddings for hybrid search, as 'provider:model'. "
            "'none' uses BM25 only (zero cost). Example: 'ollama:bge-m3'."
        ),
    )
    embedding_base_url: str | None = None
    retrieval_top_k: int = 6

    # ---------------------------------------------------------------- ingestion
    parser: Literal["auto", "pdfium", "docling"] = "auto"
    ocr_enabled: bool = Field(
        default=True, description="OCR pages without text, with Tesseract or else Docling."
    )
    ocr_language: str = "fra"
    chunk_max_chars: int = 2400
    max_upload_mb: int = 50

    # ---------------------------------------------------------------------- API
    api_key: SecretStr | None = Field(
        default=None, description="If set, every API call must send it as 'X-API-Key'."
    )
    cors_origins: list[str] = Field(default_factory=list)
    log_level: str = "INFO"
    log_json: bool = False

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'zelles.db').resolve()}"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings (cached)."""
    return Settings()
