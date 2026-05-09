"""
backend/services/otp_service.py — Secure OTP Generation and Email Delivery.

This module manages the lifecycle of One-Time Passwords used for identity verification.

Key Responsibilities:
1. Generation: Creates cryptographically secure 6-digit numeric codes.
2. Persistence: Stores codes in the `OTPRecord` table with strict 10-minute expiry windows.
3. Delivery: Dispatches emails via the Resend HTTP API (HTTPS port 443) — works on all
   cloud providers including free-tier Render (which blocks outbound SMTP ports 465/587).
4. Validation: Verifies codes, ensuring single-use consumption by deleting them after use.
"""

import random
import string
import traceback
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.models.user import OTPRecord

settings = get_settings()

OTP_EXPIRY_MINUTES = 10

RESEND_API_URL = "https://api.resend.com/emails"


def _generate_otp(length: int = 6) -> str:
    """Return a cryptographically random numeric OTP string."""
    return "".join(random.choices(string.digits, k=length))


async def generate_and_store_otp(email: str, db: AsyncSession, context: str = "signup") -> str:
    """
    Create a fresh OTP, persist it to the database, and deliver it via email.

    Args:
        email:   Destination email address.
        db:      Async database session.
        context: 'signup' or 'reset' — controls the email subject/body copy.

    Returns:
        The generated OTP code string.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Cleanup: remove any existing OTPs for this email + any globally expired ones
    await db.execute(
        delete(OTPRecord).where(
            (OTPRecord.email == email) | (OTPRecord.expires_at < now)
        )
    )

    otp_code  = _generate_otp()
    expires_at = now + timedelta(minutes=OTP_EXPIRY_MINUTES)

    record = OTPRecord(
        email=email,
        otp_code=otp_code,
        is_used=False,
        expires_at=expires_at,
    )
    db.add(record)
    await db.commit()

    # Deliver email — non-blocking best-effort; SMTP errors must NOT crash the request
    try:
        await _send_otp_email(email, otp_code, context)
    except Exception as exc:
        print(f"[OTP] Email delivery failed for {email}: {exc}")
        traceback.print_exc()

    return otp_code


async def verify_otp(email: str, code: str, db: AsyncSession) -> bool:
    """
    Validate a submitted OTP code against the database record.

    Deletes the record immediately after evaluation (single-use guarantee).

    Returns:
        True if the code is correct and not expired, False otherwise.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    result = await db.execute(
        select(OTPRecord).where(
            OTPRecord.email    == email,
            OTPRecord.otp_code == code,
        )
    )
    record = result.scalar_one_or_none()

    if record is None:
        return False

    is_valid = record.expires_at > now

    # Always delete after a verification attempt (valid or not)
    await db.delete(record)
    await db.commit()

    return is_valid


async def _send_otp_email(to_email: str, otp_code: str, context: str) -> None:
    """
    Send the OTP code using the Resend HTTP API.

    Resend communicates over standard HTTPS (port 443), which is never blocked
    by cloud providers — unlike SMTP ports 465/587 which Render blocks on free tier.
    """
    if context == "reset":
        subject = "Your DocuChat Password Reset Code"
        title   = "Reset Your DocuChat Password"
        desc    = f"Use the code below to reset your password. It expires in {OTP_EXPIRY_MINUTES} minutes."
    else:
        subject = "Your DocuChat Verification Code"
        title   = "Verify Your DocuChat Account"
        desc    = f"Use the code below to verify your email address. It expires in {OTP_EXPIRY_MINUTES} minutes."

    plain_body = (
        f"{title}\n\n"
        f"{desc}\n\n"
        f"Code: {otp_code}\n\n"
        f"If you didn't request this, you can safely ignore this email."
    )

    html_body = f"""
    <div style="font-family: Inter, sans-serif; max-width: 480px; margin: auto; padding: 32px;
                background: #121212; border-radius: 16px; color: #f5f5f5; border: 1px solid #262626;">
      <h2 style="color: #ffffff; margin-bottom: 8px;">{title}</h2>
      <p style="color: #a3a3a3; margin-bottom: 24px;">{desc}</p>
      <div style="background: #1e1e1e; border: 2px solid #525252; border-radius: 12px;
                  padding: 20px; text-align: center; letter-spacing: 12px;
                  font-size: 36px; font-weight: 700; color: #e5e5e5;">
        {otp_code}
      </div>
      <p style="margin-top: 24px; font-size: 13px; color: #737373;">
        If you didn't request this, you can safely ignore this email.
      </p>
    </div>
    """

    payload = {
        "from":    settings.email_from,
        "to":      [to_email],
        "subject": subject,
        "text":    plain_body,
        "html":    html_body,
    }

    headers = {
        "Authorization": f"Bearer {settings.resend_api_key}",
        "Content-Type":  "application/json",
    }

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(RESEND_API_URL, json=payload, headers=headers)

    if response.status_code not in (200, 201):
        raise RuntimeError(
            f"Resend API error {response.status_code}: {response.text}"
        )

    print(f"[OTP] Email sent successfully to {to_email} via Resend (id={response.json().get('id')})")
