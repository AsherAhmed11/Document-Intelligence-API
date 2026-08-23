"""
Application configuration — loaded from environment variables via .env
"""
from typing import Literal
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_name: str = "Document Intelligence API"
    app_version: str = "0.1.0"
    debug: bool = False

    # Providers & Models
    llm_provider: Literal["openai", "bytez"] = "openai"
    llm_model: str = "gpt-4o-mini"
    embedding_provider: Literal["local", "openai", "bytez"] = "local"

    # API Keys
    openai_api_key: str | None = None
    bytez_api_key: str | None = None

    # ChromaDB
    chroma_persist_directory: str = "./chroma_store"
    chroma_collection_name: str = "documents"

    # Embedding model — set this after running scripts/compare_embeddings.py
    # Options: BAAI/bge-large-en-v1.5 | BAAI/bge-base-en-v1.5 | sentence-transformers/all-MiniLM-L6-v2
    embedding_model: str = "BAAI/bge-large-en-v1.5"

    # Semantic chunker tuning — higher = fewer, larger chunks (better for dense legal text)
    # Range: 80–99. Tune by inspecting chunks on your actual documents.
    breakpoint_percentile: int = 95

    # Upload limits
    max_upload_size_mb: int = 20
    allowed_extensions: list[str] = ["pdf", "txt", "docx"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance — call this everywhere instead of instantiating Settings()."""
    return Settings()
