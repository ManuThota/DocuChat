"""
backend/models/user.py — User, OTPRecord, and UserPreferences ORM models.

Auth flow:
  SIGNUP:
    1. User submits name + email + password
    2. Account created with is_active=False, password stored as bcrypt hash
    3. OTP sent to email
    4. User verifies OTP → is_active set to True → JWT returned

  LOGIN:
    1. User submits email + password
    2. Password hash verified → JWT returned (no OTP needed)
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base

# TYPE_CHECKING is False at runtime — prevents circular imports.
# Only active when a static type checker (Pylance, mypy) analyses the file.
if TYPE_CHECKING:
    from backend.models.chat import Chat          # noqa: F401
    from backend.models.file import UploadedFile  # noqa: F401


class User(Base):
    """Registered user account. Password is stored as a bcrypt hash."""

    __tablename__ = "app_users"

    id:            Mapped[int]       = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    email:         Mapped[str]       = mapped_column(String(255), unique=True, nullable=False, index=True)
    name:          Mapped[str | None] = mapped_column(String(100), nullable=True)
    gender:        Mapped[str | None] = mapped_column(String(20), nullable=True) # 'male' | 'female' | 'other'
    profession:    Mapped[str | None] = mapped_column(String(100), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)   # bcrypt hash
    is_active:     Mapped[bool]      = mapped_column(Boolean, default=False, index=True)         # True after OTP verify
    created_at:    Mapped[datetime]  = mapped_column(DateTime, server_default=func.now(), index=True)

    # Relationships
    chats: Mapped[list[Chat]] = relationship(
        "Chat", back_populates="user", cascade="all, delete-orphan"
    )
    uploaded_files: Mapped[list[UploadedFile]] = relationship(
        "UploadedFile", back_populates="user", cascade="all, delete-orphan"
    )
    preferences: Mapped[UserPreferences] = relationship(
        "UserPreferences", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class OTPRecord(Base):
    """
    Short-lived OTP codes used only during signup email verification.
    Each code expires after 10 minutes and is single-use.
    """

    __tablename__ = "app_otp_records"

    id:         Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    email:      Mapped[str]      = mapped_column(String(255), nullable=False, index=True)
    otp_code:   Mapped[str]      = mapped_column(String(6), nullable=False)
    is_used:    Mapped[bool]     = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class UserPreferences(Base):
    """Per-user settings: theme, language, summary style."""

    __tablename__ = "app_user_preferences"

    id:           Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    user_id:      Mapped[int] = mapped_column(
        Integer, ForeignKey("app_users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    language:     Mapped[str] = mapped_column(String(20), default="English")
    theme:        Mapped[str] = mapped_column(String(10), default="dark")
    summary_mode:     Mapped[str]  = mapped_column(String(30), default="short")
    auto_delete_docs: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped[User] = relationship("User", back_populates="preferences")
