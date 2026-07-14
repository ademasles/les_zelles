"""Central backend configuration for Analyse-DCE."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    app_title: str = "Analyse-DCE API"
    debug: bool = False

    database_url: str = "sqlite:///./data/analyse_dce.db"
    storage_dir: Path = Path("./data/storage")

    parser_default: str = "docling"
    enable_ocr: bool = True
    tesseract_lang: str = "fra+eng"

    vector_store: str = "faiss"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    llm_provider: str = "ollama"
    llm_model: str = "mistral"
    ollama_base_url: str = "http://localhost:11434"

    feedback_file: Path = Path("./feedback_dataset.jsonl")
    queries_path: Path = Path("./queries.json")
    cross_encoder_model: str = "dangvantuan/CrossEncoder-camembert-large"
    cross_encoder_output_dir: Path = Path("./models/crossencoder_finetuned")

    chunk_max_chars: int = 3000
    max_context_tokens: int = 3000
    train_threshold: int = 100

    max_upload_mb: int = 50
    backend_api_url: str = "http://localhost:8000"

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
