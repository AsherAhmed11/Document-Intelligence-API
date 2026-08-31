"""
Application configuration — loaded from environment variables via .env
"""
from typing import Literal
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_name: str = "Document Intelligence API"
    app_version: str = "0.2.0"
    debug: bool = False

    # ── Providers ──────────────────────────────────────────────────────────────
    # gemini = Google Gemini API (recommended — free tier, zero local RAM)
    # openai = OpenAI API
    # local  = sentence-transformers (NOT suitable for Railway free tier)
    llm_provider: Literal["gemini", "openai", "huggingface"] = "gemini"
    llm_model: str = "gemini-3.6-flash"

    embedding_provider: Literal["gemini", "openai", "local", "huggingface"] = "gemini"
    embedding_model: str = "gemini-embedding-001"

    # ── API Keys ───────────────────────────────────────────────────────────────
    gemini_api_key: str | None = None       # Google AI Studio key
    openai_api_key: str | None = None       # Legacy / backup
    hf_api_key: str | None = None           # HuggingFace backup
    bytez_api_key: str | None = None        # Legacy

    # ── ChromaDB ───────────────────────────────────────────────────────────────
    chroma_persist_directory: str = "./chroma_store"
    chroma_collection_name: str = "documents"

    # ── Chunking ───────────────────────────────────────────────────────────────
    # Max characters per chunk (paragraph-aware, no network calls needed)
    chunk_max_chars: int = 1500
    chunk_min_chars: int = 80

    # ── Upload limits ──────────────────────────────────────────────────────────
    max_upload_size_mb: int = 20
    allowed_extensions: list[str] = ["pdf", "txt", "docx"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance — call this everywhere instead of instantiating Settings()."""
    return Settings()
