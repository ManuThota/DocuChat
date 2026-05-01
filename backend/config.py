"""
backend/config.py — Application settings loaded from environment variables.

Uses pydantic-settings to validate and provide typed access to all config.
Values are read from the .env file at project root.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All application settings sourced from environment variables."""

    # ─── Security ─────────────────────────────────────────────────────────────
    secret_key: str = "changeme-insecure-default"
    jwt_algorithm: str = "HS256"
    access_token_expire_hours: int = 24

    # ─── Database ─────────────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./docuchat.db"

    # ─── Email (SMTP) ─────────────────────────────────────────────────────────
    email_host: str = "smtp.gmail.com"
    email_port: int = 587
    email_user: str = ""
    email_pass: str = ""
    email_from: str = "DocuChat <noreply@docuchat.app>"

    # ─── HuggingFace Inference API ──────────────────────────────────────────────
    # Used for: embeddings (all-MiniLM-L6-v2) + summarization (BART)
    # Get a free key at: https://huggingface.co/settings/tokens
    hf_api_key: str = ""

    # ─── Groq API ──────────────────────────────────────────────────────────────
    # Used for: chat / Q&A (Llama-3.1-8B-Instant) — 14,400 req/day free
    # Get a free key at: https://console.groq.com/keys
    groq_api_key: str = ""

    # ─── File Uploads ─────────────────────────────────────────────────────────
    upload_dir: str = "uploads"
    max_file_size_mb: int = 10

    # ─── CORS ─────────────────────────────────────────────────────────────────
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @property
    def allowed_origins_list(self) -> list[str]:
        """Return CORS origins as a Python list."""
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def max_file_size_bytes(self) -> int:
        """Convert MB limit to bytes."""
        return self.max_file_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (singleton)."""
    return Settings()
