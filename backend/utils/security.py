"""
backend/utils/security.py — Cryptography and Authentication Primitives.

This module encapsulates all cryptographic operations, ensuring that sensitive data 
(like passwords) and identity assertions (like JWTs) are handled securely.

Responsibilities:
  - Password Hashing: Implements one-way hashing using `bcrypt` (via `passlib`).
    The chosen work factor is slow enough to resist brute-force/rainbow-table attacks, 
    but fast enough to keep login latency <200ms.
  - Token Issuance (JWT): Generates stateless JSON Web Tokens (HS256) upon successful login.
  - Token Verification: Decodes and validates JWT signatures and expiration times to assert identity.
"""

from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from backend.config import get_settings

settings = get_settings()

# ─── Password hashing ─────────────────────────────────────────────────────────
# bcrypt is the industry standard: slow enough to resist brute force,
# but fast enough for normal login (<200 ms).
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """Return a bcrypt hash of the given plain-text password."""
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return True if plain_password matches the stored bcrypt hash."""
    return _pwd_context.verify(plain_password, hashed_password)


# ─── JWT tokens ───────────────────────────────────────────────────────────────

def create_access_token(email: str) -> str:
    """
    Create a signed JWT for the given email address.

    Args:
        email: User's email — becomes the token 'sub' claim.

    Returns:
        Encoded JWT string (valid for ACCESS_TOKEN_EXPIRE_HOURS).
    """
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.access_token_expire_hours)
    payload = {
        "sub": email,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str:
    """
    Decode and validate a JWT, returning the subject (email).

    Raises:
        jwt.InvalidTokenError: If expired, tampered, or malformed.
    """
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    email: str = payload.get("sub", "")
    if not email:
        raise jwt.InvalidTokenError("Token subject is empty.")
    return email
