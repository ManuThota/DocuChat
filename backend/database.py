"""
backend/database.py — Asynchronous Database Orchestration.

This module is responsible for managing the connection lifecycle between the FastAPI application 
and the underlying relational database (SQLite for local dev, PostgreSQL/Supabase for production).

Key Components:
  - Engine: The async SQLAlchemy engine configured with connection pooling.
  - Session Factory: `AsyncSessionLocal`, used by dependencies to yield isolated database sessions.
  - Base: The `DeclarativeBase` subclass from which all ORM models inherit.
  - Initialization: `init_db()` is called during app startup to ensure all tables are created.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from backend.config import get_settings

settings = get_settings()

# ─── Engine ──────────────────────────────────────────────────────────────────
engine_kwargs = {
    "echo": False,
    "future": True,
    "pool_size": 20,
    "max_overflow": 30,
    "pool_timeout": 30,
    "pool_recycle": 1800,
    "pool_pre_ping": True,
}

# SQLAlchemy asyncpg dialect requires specific flags to disable prepared statements for PgBouncer
if settings.database_url.startswith("postgresql+asyncpg"):
    engine_kwargs["execution_options"] = {"prepared_statement_cache_size": 0}
    engine_kwargs["connect_args"] = {"statement_cache_size": 0}

engine = create_async_engine(
    settings.database_url,
    **engine_kwargs
)

# ─── Session factory ─────────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ─── Base class for ORM models ───────────────────────────────────────────────
class Base(DeclarativeBase):
    """Declarative base that all ORM models inherit from."""
    pass


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def init_db() -> None:
    """Create all tables and run migrations."""
    # Explicitly import models to ensure registration
    from backend.models.user import User, OTPRecord, UserPreferences
    from backend.models.chat import Chat, Message
    from backend.models.file import UploadedFile

    print(f"Initialising database... (Discovered {len(Base.metadata.tables)} tables)")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Migration block removed as it is no longer needed with the fresh Supabase schema.
    
    print("Database ready.")


async def get_db():
    """FastAPI dependency: yield an AsyncSession per request."""
    async with AsyncSessionLocal() as session:
        yield session
