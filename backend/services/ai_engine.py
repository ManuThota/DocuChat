"""
backend/services/ai_engine.py — AI inference wrappers.

Architecture (split by reliability on free tiers):
  ┌─────────────────────────────────────────────────────────────────┐
  │ Task            │ Provider    │ Model                           │
  │─────────────────│─────────────│─────────────────────────────────│
  │ Chat / Q&A      │ Groq API    │ llama-3.1-8b-instant            │
  │ Bullet/Exec/    │ Groq API    │ llama-3.1-8b-instant            │
  │   Study summaries│            │                                 │
  │ Short/Detailed  │ HuggingFace │ facebook/bart-large-cnn         │
  │   summaries     │ Inference   │                                 │
  │ Embeddings      │ HuggingFace │ sentence-transformers/          │
  │                 │ Inference   │   all-MiniLM-L6-v2              │
  └─────────────────────────────────────────────────────────────────┘

Why Groq for chat?
  The HuggingFace free Inference API has become too restrictive for
  chat/text-generation — models are removed or gated without warning.
  Groq provides 14,400 free requests/day with Llama 3.1 (no downloads,
  no GPU, no credit card required).

  Get a free Groq key at: https://console.groq.com/keys
  Get a free HF key at:   https://huggingface.co/settings/tokens
"""

from __future__ import annotations

from groq import Groq
from huggingface_hub import InferenceClient

from backend.config import get_settings

settings = get_settings()

# ─── Model identifiers ────────────────────────────────────────────────────────
GROQ_CHAT_MODEL     = "llama-3.1-8b-instant"   # Fast, free, great for Q&A
HF_SUMMARY_MODEL    = "facebook/bart-large-cnn" # Best abstractive summarizer


# ─── Client factories ─────────────────────────────────────────────────────────

def _groq_client() -> Groq:
    """Return a configured Groq client."""
    if not settings.groq_api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Get a free key at https://console.groq.com/keys "
            "and add GROQ_API_KEY=gsk_... to your .env file."
        )
    return Groq(api_key=settings.groq_api_key)


def _hf_client() -> InferenceClient:
    """Return a configured HuggingFace InferenceClient (embeddings + BART)."""
    if not settings.hf_api_key:
        raise RuntimeError(
            "HF_API_KEY is not set. Get a free key at https://huggingface.co/settings/tokens "
            "and add HF_API_KEY=hf_... to your .env file."
        )
    return InferenceClient(token=settings.hf_api_key)


# ─── Q&A / Chat (Groq → Llama 3.1) ──────────────────────────────────────────

def generate_answer(
    question: str,
    context: str,
    language: str = "English",
) -> str:
    """
    Generate a grounded answer using Llama-3.1-8B via Groq.

    Args:
        question: The user's question.
        context:  Retrieved document chunks. Pass "" for general questions.
        language: Target response language.

    Returns:
        AI-generated answer string.
    """
    client = _groq_client()

    if context.strip():
        system_content = (
            f"You are a helpful document assistant. Answer questions accurately "
            f"based only on the provided document context. Be concise. "
            f"Always respond in {language}. Do not use any emojis."
        )
        user_content = (
            f"Document context:\n{context[:4000]}\n\n"
            f"Question: {question}"
        )
    else:
        system_content = (
            f"You are a helpful AI assistant. Answer clearly and concisely in {language}. Do not use any emojis."
        )
        user_content = question

    response = client.chat.completions.create(
        model=GROQ_CHAT_MODEL,
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user",   "content": user_content},
        ],
        max_tokens=400,
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


# ─── Summarization ────────────────────────────────────────────────────────────

def summarize(
    text: str,
    mode: str = "short",
    language: str = "English",
) -> str:
    """
    Summarize document text.

    short / detailed  → BART-large-cnn via HuggingFace (fast, extractive)
    bullet / executive / study_notes → Llama 3.1 via Groq (follows instructions)

    Args:
        text:     Document text to summarize.
        mode:     Summary style.
        language: Output language.

    Returns:
        Summary string.
    """
    if mode in ("short", "detailed"):
        return _bart_summarize(text, mode, language)
    else:
        return _groq_summarize(text, mode, language)


def _bart_summarize(text: str, mode: str, language: str) -> str:
    """BART-based extractive summarization for short/detailed modes."""
    client = _hf_client()
    max_len = 150 if mode == "short" else 350
    min_len = 40  if mode == "short" else 120

    result = client.summarization(
        text[:4096],
        model=HF_SUMMARY_MODEL,
        max_length=max_len,
        min_length=min_len,
        do_sample=False,
    )
    summary = result.summary_text.strip()

    if language.lower() != "english":
        summary = _groq_translate(summary, language)

    return summary


def _groq_summarize(text: str, mode: str, language: str) -> str:
    """Groq-based structured summarization for bullet/executive/study modes."""
    client = _groq_client()

    instructions = {
        "bullet":      "Create a clear bullet-point summary using • for each point.",
        "executive":   "Write a professional executive summary covering key findings, decisions, and recommendations.",
        "study_notes": "Create detailed study notes with clear headings, key concepts, definitions, and examples.",
    }
    instruction = instructions.get(mode, "Summarize the following text")

    response = client.chat.completions.create(
        model=GROQ_CHAT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    f"You are an expert document analyst. "
                    f"{instruction} Respond in {language}. Do not use any emojis."
                ),
            },
            {
                "role": "user",
                "content": f"Document:\n\n{text[:4000]}",
            },
        ],
        max_tokens=600,
        temperature=0.4,
    )
    return response.choices[0].message.content.strip()


def _groq_translate(text: str, language: str) -> str:
    """Translate text to the target language using Groq."""
    client = _groq_client()
    response = client.chat.completions.create(
        model=GROQ_CHAT_MODEL,
        messages=[
            {"role": "system", "content": f"Translate the following text to {language}. Return only the translation."},
            {"role": "user",   "content": text},
        ],
        max_tokens=500,
        temperature=0.1,
    )
    return response.choices[0].message.content.strip()


def generate_title(user_message: str, assistant_reply: str = "") -> str:
    """
    Generate a very short (2-4 words) title for a conversation based on the first message and reply.
    """
    try:
        client = _groq_client()
        content_prompt = f"User: {user_message}\n"
        if assistant_reply:
            content_prompt += f"Assistant: {assistant_reply[:500]}\n"
            
        response = client.chat.completions.create(
            model=GROQ_CHAT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant. Generate a very concise title (maximum 4 words) for a conversation based on the user's request and the assistant's reply. Return only the title text, no quotes, no emojis, and no prefix."
                },
                {"role": "user", "content": content_prompt},
            ],
            max_tokens=20,
            temperature=0.5,
        )
        title = response.choices[0].message.content.strip()
        # Clean up any quotes
        return title.replace('"', '').replace("'", "")
    except Exception:
        # Fallback to simple truncation
        return user_message[:30] + "..."
