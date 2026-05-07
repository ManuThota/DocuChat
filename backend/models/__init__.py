# backend/models/__init__.py
from backend.models.user import User, OTPRecord, UserPreferences
from backend.models.chat import Chat, Message
from backend.models.file import UploadedFile

__all__ = [
    "User",
    "OTPRecord",
    "UserPreferences",
    "Chat",
    "Message",
    "UploadedFile",
]
