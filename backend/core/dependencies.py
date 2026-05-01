"""
backend/core/dependencies.py — FastAPI dependency injection helpers.

get_current_user:
  Extracts the JWT from the Authorization header, decodes it,
  and returns the corresponding User ORM object.
  Used via `Depends(get_current_user)` in any protected route.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import jwt

from backend.database import get_db
from backend.models.user import User
from backend.utils.security import decode_access_token

# Bearer token extractor — reads Authorization: Bearer <token>
bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Validate JWT and return the authenticated user.

    Raises:
        401 if token is invalid / expired.
        401 if user no longer exists in DB.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        email = decode_access_token(credentials.credentials)
    except jwt.InvalidTokenError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise credentials_exception

    return user
