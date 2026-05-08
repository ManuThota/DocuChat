"""
backend/database.py — Async SQLAlchemy engine + session factory.

Uses aiosqlite for SQLite in dev, asyncpg for PostgreSQL in prod.
All tables are created on startup via init_db().
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from backend.config import get_settings

settings = get_settings()

# ─── Engine ──────────────────────────────────────────────────────────────────
engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    # connection pooling
    pool_size=20,
    max_overflow=30,
    pool_timeout=30,
    pool_recycle=1800,
    # validates dead connections
    pool_pre_ping=True,
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
