"""
backend/routers/export.py — PDF export endpoint.

  POST /export/pdf — Generate and stream a PDF of the chat conversation
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.dependencies import get_current_user
from backend.database import get_db
from backend.models.chat import Chat
from backend.models.user import User
from backend.services.export_service import generate_chat_pdf

router = APIRouter(prefix="/export", tags=["Export"])


class ExportPDFRequest(BaseModel):
    chat_id: int


@router.post("/pdf")
async def export_pdf(
    body:         ExportPDFRequest,
    current_user: User            = Depends(get_current_user),
    db:           AsyncSession    = Depends(get_db),
):
    """
    Generate a styled PDF of the requested chat and return it as a download.
    """
    result = await db.execute(
        select(Chat)
        .options(selectinload(Chat.messages))
        .where(Chat.id == body.chat_id, Chat.user_id == current_user.id)
    )
    chat = result.scalar_one_or_none()

    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found.")

    messages = [
        {"role": m.role, "content": m.content}
        for m in chat.messages
    ]

    pdf_bytes = generate_chat_pdf(chat.title, messages)

    filename = f"docuchat_{chat.id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
