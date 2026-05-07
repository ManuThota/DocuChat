"""
backend/services/otp_service.py — OTP generation and email delivery.

Flow:
  1. generate_and_store_otp(email, db) — creates a 6-digit code, persists it,
     and sends it via SMTP.
  2. verify_otp(email, code, db) — checks the code, marks it used, returns bool.

Security:
  - OTP codes expire after 10 minutes (configurable).
  - Each code is single-use (is_used flag).
  - Old unused codes for the same email are invalidated on new request.
"""

import random
import string
from datetime import datetime, timedelta, timezone

import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.models.user import OTPRecord

settings = get_settings()

OTP_EXPIRY_MINUTES = 10


def _generate_otp(length: int = 6) -> str:
    """Return a random numeric OTP string."""
    return "".join(random.choices(string.digits, k=length))


async def generate_and_store_otp(email: str, db: AsyncSession, context: str = "signup") -> str:
    """
    Create a fresh OTP, save it to the database, and email it to the user.

    Args:
        email: Destination email address.
        db:    Async database session.
        context: Context of the OTP ("signup" or "reset").

    Returns:
        The generated OTP code (for testing / logging — do NOT expose in API response).
    """
    from sqlalchemy import delete
    now = datetime.now(timezone.utc)

    # 1. Cleanup: Delete all prior OTPs for this specific email
    # 2. Cleanup: Delete ALL expired OTPs from the database (Global hygiene)
    await db.execute(
        delete(OTPRecord).where(
            (OTPRecord.email == email) | (OTPRecord.expires_at < now)
        )
    )

    otp_code = _generate_otp()
    expires_at = now + timedelta(minutes=OTP_EXPIRY_MINUTES)

    record = OTPRecord(
        email=email,
        otp_code=otp_code,
        is_used=False,
        expires_at=expires_at,
    )
    db.add(record)
    await db.commit()

    # Send email (best-effort; don't let SMTP errors crash the request)
    try:
        await _send_otp_email(email, otp_code, context)
    except Exception as exc:
        print(f"[OTP] Email delivery failed for {email}: {exc}")

    return otp_code


async def verify_otp(email: str, code: str, db: AsyncSession) -> bool:
    """
    Check whether the given OTP code is valid for the email address.

    Deletes the code immediately after the attempt (instant cleanup & security).

    Returns:
        True if valid and not expired, False otherwise.
    """
    now = datetime.now(timezone.utc)
    
    # Fetch the record regardless of expiration to ensure we can delete it after the attempt
    result = await db.execute(
        select(OTPRecord).where(
            OTPRecord.email == email,
            OTPRecord.otp_code == code
        )
    )
    record = result.scalar_one_or_none()

    if record is None:
        return False

    # Check validity before deleting
    is_valid = record.expires_at > now

    # Delete the record immediately (it's been "validated" now, so it must be gone)
    await db.delete(record)
    await db.commit()

    return is_valid


async def _send_otp_email(to_email: str, otp_code: str, context: str) -> None:
    """Send the OTP code via SMTP."""
    msg = MIMEMultipart("alternative")
    
    if context == "reset":
        subject = "Your DocuChat Password Update Code"
        title = "Your DocuChat Password Update Code"
        desc = f"Use the code below to change your password. It expires in {OTP_EXPIRY_MINUTES} minutes."
    else:
        subject = "Your DocuChat Account Verification Code"
        title = "Verify Your DocuChat Account"
        desc = f"Use the code below to verify your email address. It expires in {OTP_EXPIRY_MINUTES} minutes."

    msg["Subject"] = subject
    msg["From"] = settings.email_from
    msg["To"] = to_email

    html_body = f"""
    <div style="font-family: Inter, sans-serif; max-width: 480px; margin: auto; padding: 32px;
                background: #121212; border-radius: 16px; color: #f5f5f5; border: 1px solid #262626;">
      <h2 style="color: #ffffff; margin-bottom: 8px;">{title}</h2>
      <p style="color: #a3a3a3; margin-bottom: 24px;">
        {desc}
      </p>
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

    msg.attach(MIMEText(html_body, "html"))

    await aiosmtplib.send(
        msg,
        hostname=settings.email_host,
        port=settings.email_port,
        username=settings.email_user,
        password=settings.email_pass,
        start_tls=True,
    )
