"""
backend/config.py — Global Application Settings.

This module leverages `pydantic-settings` to provide strongly-typed, validated access to all 
environment variables. Values are securely loaded from the `.env` file at the project root 
(or the runtime environment variables in production).

Using a centralized `Settings` class ensures that missing or malformed configuration values 
are caught immediately at startup rather than causing unexpected runtime crashes.
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

    # ─── Email (Resend HTTP API) ──────────────────────────────────────────────
    # SMTP is blocked on most free cloud tiers; Resend uses HTTPS (port 443).
    # Get a free key at: https://resend.com (3,000 emails/month free)
    resend_api_key: str = ""
    email_from: str = "DocuChat <onboarding@resend.dev>"

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
    max_file_size_mb: int = 50

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
