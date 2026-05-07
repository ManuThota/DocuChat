"""
backend/routers/user.py — User profile and preferences endpoints.

  GET   /user/profile      — Return current user info + preferences
  PATCH /user/preferences  — Update language, theme, summary_mode
"""

import os
import shutil
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.core.dependencies import get_current_user
from backend.database import get_db
from backend.models.user import User, UserPreferences

settings = get_settings()
router = APIRouter(prefix="/user", tags=["User"])

class PreferencesUpdate(BaseModel):
    language:         str | None = None
    theme:            str | None = None
    summary_mode:     str | None = None
    auto_delete_docs: bool | None = None


from backend.utils.security import verify_password, hash_password

class ProfileUpdate(BaseModel):
    name:             str | None = None
    gender:           str | None = None
    profession:       str | None = None
    current_password: str | None = None
    new_password:     str | None = None

@router.get("/profile")
async def get_profile(
    current_user: User        = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    """Return the authenticated user's profile and saved preferences."""
    result = await db.execute(
        select(User)
        .options(selectinload(User.preferences))
        .where(User.id == current_user.id)
    )
    user = result.scalar_one_or_none()

    prefs = user.preferences
    return {
        "id":         user.id,
        "email":      user.email,
        "name":       user.name,
        "gender":     user.gender,
        "profession": user.profession,
        "created_at": user.created_at.isoformat(),
        "preferences": {
            "language":         prefs.language         if prefs else "English",
            "theme":            prefs.theme            if prefs else "dark",
            "summary_mode":     prefs.summary_mode     if prefs else "short",
            "auto_delete_docs": prefs.auto_delete_docs if prefs else False,
        },
    }

@router.patch("/profile")
async def update_profile(
    body:         ProfileUpdate,
    current_user: User            = Depends(get_current_user),
    db:           AsyncSession    = Depends(get_db),
):
    """Update user profile info (name, gender, password)."""
    result = await db.execute(
        select(User).where(User.id == current_user.id)
    )
    user = result.scalar_one_or_none()

    if body.name is not None:
        user.name = body.name
    if body.gender is not None:
        user.gender = body.gender
    if body.profession is not None:
        user.profession = body.profession

    if body.new_password:
        if not body.current_password or not verify_password(body.current_password, user.password_hash):
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Invalid current password.")
        user.password_hash = hash_password(body.new_password)

    await db.commit()
    await db.refresh(user)

    return {
        "id":         user.id,
        "email":  user.email,
        "name":   user.name,
        "gender": user.gender,
        "profession": user.profession,
    }


@router.patch("/preferences")
async def update_preferences(
    body:         PreferencesUpdate,
    current_user: User            = Depends(get_current_user),
    db:           AsyncSession    = Depends(get_db),
):
    """Update one or more user preference fields."""
    result = await db.execute(
        select(UserPreferences).where(UserPreferences.user_id == current_user.id)
    )
    prefs = result.scalar_one_or_none()

    if prefs is None:
        # Create default preferences if missing
        prefs = UserPreferences(user_id=current_user.id)
        db.add(prefs)

    if body.language is not None:
        prefs.language = body.language
    if body.theme is not None:
        prefs.theme = body.theme
    if body.summary_mode is not None:
        prefs.summary_mode = body.summary_mode
    if body.auto_delete_docs is not None:
        prefs.auto_delete_docs = body.auto_delete_docs

    await db.commit()
    await db.refresh(prefs)

    return {
        "language":         prefs.language,
        "theme":            prefs.theme,
        "summary_mode":     prefs.summary_mode,
        "auto_delete_docs": prefs.auto_delete_docs,
    }
@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_account(
    current_user: User        = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    """Permanently delete user account and all associated data."""
    # 1. Delete physical files and indices
    user_dir = os.path.join(settings.upload_dir, str(current_user.id))
    if os.path.exists(user_dir):
        # shutil.rmtree removes the directory and all its contents
        shutil.rmtree(user_dir)

    # 2. Delete user from DB (Cascades will handle related records if configured, 
    # but let's be explicit if needed. The model has ForeignKey(..., ondelete="CASCADE"))
    await db.delete(current_user)
    await db.commit()

    return None
