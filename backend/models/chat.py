"""
backend/models/chat.py — Chat session and Message ORM models.

A Chat belongs to a User and contains many Messages.
Messages have role='user' or role='assistant'.
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
    from backend.models.user import User          # noqa: F401
    from backend.models.file import UploadedFile  # noqa: F401


class Chat(Base):
    """A conversation session. Each user can have many chats."""

    __tablename__ = "app_chats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), default="New Chat")
    is_archived: Mapped[bool] = mapped_column(default=False)
    is_hidden: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="chats")
    messages: Mapped[list[Message]] = relationship(
        "Message", back_populates="chat", cascade="all, delete-orphan", order_by="Message.created_at"
    )
    uploaded_files: Mapped[list[UploadedFile]] = relationship(
        "UploadedFile", back_populates="chat", cascade="all, delete-orphan"
    )


class Message(Base):
    """A single turn in a chat (user prompt or assistant reply)."""

    __tablename__ = "app_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("app_chats.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(10), nullable=False)  # 'user' | 'assistant'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    chat: Mapped["Chat"] = relationship("Chat", back_populates="messages")
