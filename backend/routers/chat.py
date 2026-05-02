"""
backend/routers/chat.py — Chat session and messaging endpoints.

  POST   /chat/new         — Create a new chat session
  POST   /chat/message     — Send a message, get AI reply (RAG or summarize)
  GET    /chat/history     — List all chats for the current user
  GET    /chat/{chat_id}   — Get a single chat + all its messages
  DELETE /chat/{chat_id}   — Delete a chat and its messages
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.dependencies import get_current_user
from backend.database import get_db
from backend.models.chat import Chat, Message
from backend.models.file import UploadedFile
from backend.models.user import User
from backend.services.rag_pipeline import answer_question, summarize_document

import os
from backend.config import get_settings

settings = get_settings()
router = APIRouter(prefix="/chat", tags=["Chat"])


# ─── Schemas ─────────────────────────────────────────────────────────────────

class NewChatRequest(BaseModel):
    title: str = "New Chat"


class SendMessageRequest(BaseModel):
    chat_id:      int
    content:      str
    file_id:      int | None = None
    language:     str        = "English"
    summary_mode: str | None = None   # None → Q&A mode


class ChatUpdate(BaseModel):
    title:       str | None = None
    is_archived: bool | None = None
    is_hidden:   bool | None = None



# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/new", status_code=status.HTTP_201_CREATED)
async def new_chat(
    body:         NewChatRequest  = NewChatRequest(),
    current_user: User            = Depends(get_current_user),
    db:           AsyncSession    = Depends(get_db),
):
    """Create a new chat session for the authenticated user."""
    chat = Chat(user_id=current_user.id, title=body.title)
    db.add(chat)
    await db.commit()
    await db.refresh(chat)
    return {"id": chat.id, "title": chat.title, "created_at": chat.created_at.isoformat()}


@router.post("/message")
async def send_message(
    body:         SendMessageRequest,
    current_user: User            = Depends(get_current_user),
    db:           AsyncSession    = Depends(get_db),
):
    """
    Send a user message and receive an AI-generated reply.

    If a file_id is provided, the RAG pipeline is used to answer from the document.
    If a summary_mode is set, the document is summarised instead.
    """
    # ─── Validate chat ownership ──────────────────────────────────────────────
    result = await db.execute(
        select(Chat).where(Chat.id == body.chat_id, Chat.user_id == current_user.id)
    )
    chat = result.scalar_one_or_none()
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found.")

    # ─── Fetch recent context ─────────────────────────────────────────────────
    # We load the last 8 messages to provide conversational memory
    hist_res = await db.execute(
        select(Message)
        .where(Message.chat_id == chat.id)
        .order_by(Message.created_at.desc())
        .limit(8)
    )
    history = [
        {"role": m.role, "content": m.content}
        for m in reversed(hist_res.scalars().all())
    ]

    # ─── Persist user message ─────────────────────────────────────────────────
    user_msg = Message(chat_id=chat.id, role="user", content=body.content)
    db.add(user_msg)

    # ─── Resolve FAISS index path ─────────────────────────────────────────────
    index_path: str | None = None
    if body.file_id:
        file_result = await db.execute(
            select(UploadedFile).where(
                UploadedFile.id == body.file_id,
                UploadedFile.user_id == current_user.id,
            )
        )
        uploaded_file = file_result.scalar_one_or_none()
        if uploaded_file:
            index_path = uploaded_file.faiss_index_path

    # ─── AI generation ────────────────────────────────────────────────────────
    try:
        if body.summary_mode and index_path:
            ai_text = summarize_document(index_path, mode=body.summary_mode, language=body.language)
        elif index_path:
            ai_text = answer_question(body.content, index_path, language=body.language, history=history)
        else:
            # No document context — use model's own knowledge
            from backend.services.ai_engine import generate_answer
            ai_text = generate_answer(body.content, context="", language=body.language, history=history)
    except Exception as exc:
        print(f"[Chat] AI generation failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI service error: {str(exc)}"
        )

    # ─── Persist assistant reply ──────────────────────────────────────────────
    asst_msg = Message(chat_id=chat.id, role="assistant", content=ai_text)
    db.add(asst_msg)

    # Update chat title automatically if it's the first message
    if chat.title == "New Chat":
        from backend.services.ai_engine import generate_title
        chat.title = generate_title(body.content, ai_text)

    await db.commit()
    await db.refresh(asst_msg)

    return {
        "user_message":      {"role": "user",      "content": body.content},
        "assistant_message": {"role": "assistant",  "content": ai_text, "id": asst_msg.id},
    }


@router.get("/history")
async def chat_history(
    current_user: User        = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    """Return all chat sessions for the current user, newest first."""
    result = await db.execute(
        select(Chat)
        .where(Chat.user_id == current_user.id)
        .order_by(Chat.updated_at.desc())
    )
    chats = result.scalars().all()
    return [
        {
            "id": c.id, 
            "title": c.title, 
            "is_archived": c.is_archived,
            "is_hidden": c.is_hidden,
            "created_at": c.created_at.isoformat()
        }
        for c in chats
    ]



@router.get("/{chat_id}")
async def get_chat(
    chat_id:      int,
    current_user: User        = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    """Return a single chat with all its messages."""
    result = await db.execute(
        select(Chat)
        .options(selectinload(Chat.messages))
        .where(Chat.id == chat_id, Chat.user_id == current_user.id)
    )
    chat = result.scalar_one_or_none()
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found.")

    return {
        "id":       chat.id,
        "title":    chat.title,
        "is_archived": chat.is_archived,
        "is_hidden":   chat.is_hidden,
        "messages": [
            {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at.isoformat()}
            for m in chat.messages
        ],
    }



@router.patch("/{chat_id}")
async def update_chat(
    chat_id:      int,
    body:         ChatUpdate,
    current_user: User        = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    """Update chat title, archived status, or hidden status."""
    result = await db.execute(
        select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id)
    )
    chat = result.scalar_one_or_none()
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found.")

    if body.title is not None:
        chat.title = body.title
    if body.is_archived is not None:
        chat.is_archived = body.is_archived
    if body.is_hidden is not None:
        chat.is_hidden = body.is_hidden

    await db.commit()
    await db.refresh(chat)
    return {
        "id": chat.id,
        "title": chat.title,
        "is_archived": chat.is_archived,
        "is_hidden": chat.is_hidden
    }


import os
from backend.models.file import UploadedFile

@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
    chat_id:      int,
    current_user: User        = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    """Delete a chat and cascade-delete all messages and documents."""
    result = await db.execute(
        select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id)
    )
    chat = result.scalar_one_or_none()
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found.")

    # Physically delete associated documents
    files_result = await db.execute(
        select(UploadedFile).where(UploadedFile.chat_id == chat_id)
    )
    files = files_result.scalars().all()
    user_dir = os.path.join(settings.upload_dir, str(current_user.id))
    
    for f in files:
        if f.stored_name:
            file_path = os.path.join(user_dir, f.stored_name)
            if os.path.exists(file_path):
                os.remove(file_path)
        if f.faiss_index_path:
            # faiss_index_path is the prefix. Actual files have .faiss and .chunks
            f_idx = f.faiss_index_path + ".faiss"
            f_chk = f.faiss_index_path + ".chunks"
            if os.path.exists(f_idx): os.remove(f_idx)
            if os.path.exists(f_chk): os.remove(f_chk)

    await db.delete(chat)
    await db.commit()

