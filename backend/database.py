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
    echo=False,       # Set True to log all SQL (debug only)
    future=True,
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
    from backend.models import user, chat, file  # noqa: F401

    print("Initialising database...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # ─── MIGRATION: Add is_archived and is_hidden to chats ─────────────────
    async with engine.begin() as conn:
        try:
            await conn.execute(text("ALTER TABLE chats ADD COLUMN is_archived BOOLEAN DEFAULT 0"))
            print("Added 'is_archived' column to 'chats'")
        except Exception:
            pass # Already exists

        try:
            await conn.execute(text("ALTER TABLE chats ADD COLUMN is_hidden BOOLEAN DEFAULT 0"))
            print("Added 'is_hidden' column to 'chats'")
        except Exception:
            pass # Already exists

        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN profession VARCHAR(100)"))
            print("Added 'profession' column to 'users'")
        except Exception:
            pass # Already exists
    
    print("Database ready.")


async def get_db():
    """FastAPI dependency: yield an AsyncSession per request."""
    async with AsyncSessionLocal() as session:
        yield session
