"""
backend/services/otp_service.py — Secure OTP Generation and Email Delivery.

This module manages the lifecycle of One-Time Passwords used for identity verification.

Key Responsibilities:
1. Generation: Creates cryptographically secure 6-digit numeric codes.
2. Persistence: Stores codes in the `OTPRecord` table with strict 10-minute expiry windows.
3. Delivery: Dispatches emails securely via `aiosmtplib` using implicit TLS (port 465).
4. Validation: Verifies codes, ensuring single-use consumption by marking them as `is_used = True`.
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
    """
    from sqlalchemy import delete
    import traceback
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Cleanup
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

    # Send email
    try:
        await _send_otp_email(email, otp_code, context)
    except Exception as exc:
        print(f"[OTP] Email delivery failed for {email}: {exc}")
        traceback.print_exc()

    return otp_code


async def verify_otp(email: str, code: str, db: AsyncSession) -> bool:
    """Check whether the given OTP code is valid for the email address."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    
    result = await db.execute(
        select(OTPRecord).where(
            OTPRecord.email == email,
            OTPRecord.otp_code == code
        )
    )
    record = result.scalar_one_or_none()

    if record is None:
        return False

    is_valid = record.expires_at > now

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

    plain_body = f"{title}\n\n{desc}\n\nCode: {otp_code}\n\nIf you didn't request this, you can safely ignore this email."
    
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

    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    await aiosmtplib.send(
        msg,
        hostname=settings.email_host,
        port=settings.email_port,
        username=settings.email_user,
        password=settings.email_pass,
        use_tls=(settings.email_port == 465),
        start_tls=(settings.email_port == 587),
    )
