"""
backend/main.py — DocuChat FastAPI Application Entry Point.

Run with:
  uvicorn backend.main:app --reload --port 8000

Production:
  gunicorn backend.main:app -w 4 -k uvicorn.workers.UvicornWorker
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.config import get_settings
from backend.database import init_db
from backend.routers import auth, chat, upload, export, user

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    # Create database tables
    await init_db()
    # Create uploads directory
    os.makedirs(settings.upload_dir, exist_ok=True)
    print("DocuChat API is ready.")
    yield
    print("DocuChat API is shutting down.")


app = FastAPI(
    title="DocuChat API",
    description="AI-powered document chat and summarization platform.",
    version="1.0.0",
    lifespan=lifespan,
)

# ─── CORS ────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ─────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(upload.router)
app.include_router(export.router)
app.include_router(user.router)


@app.get("/health", tags=["Health"])
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "version": "1.0.0"}


@app.get("/")
async def root():
    """Redirect root to the frontend login page."""
    return RedirectResponse(url="/pages/index.html")


# ─── Serve Frontend ──────────────────────────────────────────────────────────
frontend_dir = Path(__file__).parent.parent / "frontend"

if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
else:
    print(f"⚠️ Warning: Frontend directory not found at {frontend_dir}")
