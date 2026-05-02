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
    history: list[dict] | None = None,
) -> str:
    """
    Generate a grounded answer using Llama-3.1-8B via Groq.

    Args:
        question: The user's question.
        context:  Retrieved document chunks. Pass "" for general questions.
        language: Target response language.
        history:  List of previous messages: [{"role": "user", "content": "..."}, ...]

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

    messages = [{"role": "system", "content": system_content}]
    if history:
        # Only take last 10 messages to avoid token limits
        messages.extend(history[-10:])
    messages.append({"role": "user", "content": user_content})

    response = client.chat.completions.create(
        model=GROQ_CHAT_MODEL,
        messages=messages,
        max_tokens=2048, # Increased from 400 to prevent truncation
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
    Summarize document text using a hybrid Map-Reduce approach.
    
    Small documents (<18k chars) are processed in one shot via Groq.
    Large documents are chunked, summarized via HuggingFace BART (Map),
    and then refined by Groq Llama 3.1 (Reduce).
    """
    if len(text) < 18000:
        return _groq_summarize(text, mode, language)
        
    # Large document logic (Map-Reduce)
    chunk_size = 12000
    intermediate_summaries = []
    
    # Map Step: Fast extractive summary for each chunk
    for i in range(0, min(len(text), 200000), chunk_size):
        chunk = text[i:i+chunk_size]
        try:
            summary = _hf_fast_summary(chunk)
            if summary:
                intermediate_summaries.append(summary)
        except Exception:
            # Fallback: take first sentence if HF fails
            intermediate_summaries.append(chunk[:300] + "...")
            
    combined_text = "\n\n".join(intermediate_summaries)
    
    # Reduce Step: Final intelligent summary via Groq
    return _groq_summarize(combined_text, mode, language)


def _hf_fast_summary(text: str) -> str:
    """Direct POST to HF Inference API for fast extractive chunking."""
    import json
    client = _hf_client()
    
    payload = {
        "inputs": text[:4000],
        "parameters": {"max_length": 250, "min_length": 50, "do_sample": False}
    }
    
    # Use low-level post to avoid InferenceClient keyword issues
    response_bytes = client.post(json=payload, model=HF_SUMMARY_MODEL)
    res = json.loads(response_bytes.decode("utf-8"))
    
    if isinstance(res, list) and len(res) > 0:
        return res[0].get("summary_text", "")
    elif isinstance(res, dict):
        return res.get("summary_text", "")
    return ""


def _groq_summarize(text: str, mode: str, language: str) -> str:
    """Llama 3.1-based summarization via Groq for all modes."""
    client = _groq_client()
    
    instructions = {
        "short":       "Provide a concise 1-2 paragraph summary of the text.",
        "detailed":    "Provide a comprehensive, multi-paragraph summary covering all main points in detail.",
        "bullet":      "Summarize the text into clear, high-level bullet points using Markdown.",
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
                    f"Your task is to: {instruction}. "
                    f"IMPORTANT: You must process the ENTIRE provided text and ensure no key details are missed. "
                    f"Respond in {language}. Do not use any emojis. "
                    f"Format the output clearly using Markdown."
                ),
            },
            {
                "role": "user",
                "content": f"Document Text:\n\n{text[:20000]}",
            },
        ],
        max_tokens=2048,
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
        max_tokens=1500, # Increased for translations
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
