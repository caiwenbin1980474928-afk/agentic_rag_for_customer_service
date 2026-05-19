"""Centralized configuration loaded from .env via pydantic-settings.

Note on caching: ``get_settings()`` is **not** memoised. Constructing a
``Settings`` instance is < 100µs (pydantic parses ~10 short string env vars),
and skipping the cache lets ``.env`` changes take effect on the next call
without restarting the process — handy when iterating on ``MAX_RETRIES`` /
``TOP_K`` during dev. Hot path code is expected to bind once at module load
anyway, so the no-cache cost is negligible.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    openai_base_url: str | None = "https://open.bigmodel.cn/api/paas/v4/"

    llm_model: str = "glm-4-flash"
    embed_model: str = "embedding-3"

    top_k: int = 4
    max_retries: int = 3

    chroma_dir: str = "./.chroma"
    docs_dir: str = "./data/sample_docs"
    collection_name: str = "agentic_rag_kb"

    host: str = "0.0.0.0"
    port: int = 8000

    @property
    def chroma_path(self) -> Path:
        return Path(self.chroma_dir).resolve()

    @property
    def docs_path(self) -> Path:
        return Path(self.docs_dir).resolve()


def get_settings() -> Settings:
    """Build a fresh ``Settings`` instance from ``.env`` (no memoisation).

    Cheap enough to call per-request; not cached on purpose, see module docstring.
    """
    return Settings()
