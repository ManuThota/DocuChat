"""
backend/models/file.py — UploadedFile ORM model.

Each uploaded file is linked to a user and optionally to a chat.
The FAISS index path is stored here so the RAG pipeline can load it.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base

# TYPE_CHECKING is False at runtime — prevents circular imports.
# Only active when a static type checker (Pylance, mypy) analyses the file.
if TYPE_CHECKING:
    from backend.models.user import User  # noqa: F401
    from backend.models.chat import Chat  # noqa: F401


class UploadedFile(Base):
    """Metadata for a user-uploaded document."""

    __tablename__ = "app_uploaded_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chat_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("app_chats.id", ondelete="CASCADE"), nullable=True, index=True
    )
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False)  # UUID-based filename
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)     # pdf|docx|txt|png|jpg
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)        # bytes
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    faiss_index_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="uploaded_files")
    chat: Mapped[Chat | None] = relationship("Chat", back_populates="uploaded_files")
