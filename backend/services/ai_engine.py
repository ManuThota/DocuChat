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
    return Groq(api_key=settings.groq_api_key, timeout=20.0, max_retries=0)


def _hf_client() -> InferenceClient:
    """Return a configured HuggingFace InferenceClient (embeddings + BART)."""
    if not settings.hf_api_key:
        raise RuntimeError(
            "HF_API_KEY is not set. Get a free key at https://huggingface.co/settings/tokens "
            "and add HF_API_KEY=hf_... to your .env file."
        )
    return InferenceClient(token=settings.hf_api_key, timeout=20.0)


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
            f"You are a highly intelligent and targeted document assistant. "
            f"Provide answers in {language}. "
            f"STRICT RULES:\n"
            f"1. **STRICT FAITHFULNESS**: ONLY use the provided DOCUMENT CONTEXT. If the user's question is NOT related to the document context, you MUST explicitly state: 'This topic is not discussed in the document, but based on my general knowledge...' before answering.\n"
            f"2. **NO HALLUCINATIONS**: Do NOT provide code or programs unless they appear verbatim in the context.\n"
            f"3. **RICH FORMATTING**: Use bold text for key terms, bullet points for lists, and clear headers to organize information. Format your response to look professional and easy to read (like ChatGPT).\n"
            f"4. **TECHNICAL DETAILS**: Include all relevant examples, commands, and technical steps found in the context.\n"
            f"5. **SPECIFICITY**: Focus ONLY on the requested topic. Do NOT provide overviews or summaries of other document sections.\n"
            f"6. **DIRECT START**: Start your response immediately with the answer. No 'Based on the context...' or 'The document states...' introductions.\n"
            f"7. Do not use emojis. Use Markdown code blocks for all code."
        )
        user_content = (
            f"DOCUMENT CONTEXT:\n{context[:12000]}\n\n"
            f"USER QUESTION: {question}"
        )
    else:
        system_content = (
            f"You are a helpful AI assistant. Answer clearly and concisely in {language}. "
            f"Do not use any emojis. Use Markdown formatting."
        )
        user_content = question

    messages = [{"role": "system", "content": system_content}]
    if history:
        messages.extend(history[-10:])
    messages.append({"role": "user", "content": user_content})

    response = client.chat.completions.create(
        model=GROQ_CHAT_MODEL,
        messages=messages,
        max_tokens=2048,
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
    Summarize document text using an optimized Fast Map-Reduce approach.
    
    Optimized to prevent timeouts and stay under Groq's 6k TPM limit.
    """
    if len(text) < 15000:
        return _groq_summarize(text, mode, language)
        
    # Large document logic (Map-Reduce)
    # Larger chunks (15k) reduce the number of API calls significantly
    chunk_size = 15000
    intermediate_summaries = []
    
    # Process up to 200k characters for a fast, comprehensive result
    max_scan = 200000
    for i in range(0, min(len(text), max_scan), chunk_size):
        chunk = text[i:i+chunk_size]
        try:
            # Groq 8B is much faster for the map phase
            summary = _groq_mini_summary(chunk, language)
            
            # Silent fallback to HF if Groq is busy
            if not summary:
                summary = _hf_fast_summary(chunk[:3000])
            
            if summary:
                intermediate_summaries.append(summary)
        except Exception as e:
            print(f"[AI] Chunk {i} map failed: {e}")
            
    if not intermediate_summaries:
        combined_text = text[:8000] 
    else:
        combined_text = "\n\n".join(intermediate_summaries)
    
    # Final Synthesis (Stay safe under 6k TPM)
    return _groq_summarize(combined_text[:10000], mode, language)


def _hf_fast_summary(text: str) -> str:
    """Use Hugging Face InferenceClient's summarization task."""
    try:
        client = _hf_client()
        # BART has a 1024 token limit (~3500 chars). We use 3000 to be safe.
        # Passing only text and model to ensure compatibility with all HF library versions
        result = client.summarization(
            text[:3000],
            model=HF_SUMMARY_MODEL
        )
        
        # result is typically a dict with 'summary_text' or a list containing such a dict
        if isinstance(result, list) and len(result) > 0:
            return result[0].get("summary_text", "")
        if isinstance(result, dict):
            return result.get("summary_text", "")
        return str(result)
    except Exception as e:
        print(f"[HF] Task failed: {e}")
    return ""


def _groq_mini_summary(text: str, language: str) -> str:
    """Ultra-fast, low-token summary to act as a fallback."""
    try:
        client = _groq_client()
        response = client.chat.completions.create(
            model="llama-3-8b-8192", 
            messages=[
                {"role": "system", "content": f"Summarize VERY briefly (max 40 words) in {language}. List headings if found."},
                {"role": "user", "content": text[:6000]}
            ],
            max_tokens=100,
            temperature=0.1,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return ""


def _groq_summarize(text: str, mode: str, language: str) -> str:
    """Llama 3.1-based summarization via Groq for all modes."""
    client = _groq_client()
    
    if not text.strip():
        return "The document appears to be empty or unreadable."

    instructions = {
        "short":       "Provide a concise 1-2 paragraph summary.",
        "detailed":    "Create an exhaustive, chronological map of the document. Group sections under '## Chapter [X]' or '## [Main Topic]' headers. Format every entry as '### **Section [Number]: [Title]** - [Overview]'.",
        "bullet":      "Summarize the text into clear bullet points with bold key terms.",
        "executive":   "Write a professional executive summary for high-level stakeholders.",
        "study_notes": "Create highly structured study notes with headings, bold definitions, and examples.",
    }
    instruction = instructions.get(mode, "Summarize the following text")

    response = client.chat.completions.create(
        model=GROQ_CHAT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    f"You are a professional document analyst. "
                    f"Your task is to: {instruction}. "
                    f"STRICT RULES (CRITICAL):\n"
                    f"1. **STRICT CHRONOLOGY**: You must follow the document's flow from the very first line to the very last. NEVER skip around.\n"
                    f"2. **CONTINUOUS FLOW**: Treat the text as a single sequence. If multiple chapters appear, use clear ## headers to separate them.\n"
                    f"3. **PREMIUM FORMATTING**: Use bold headers and clean spacing. Every section overview must be factual and specific.\n"
                    f"4. **CONSOLIDATION**: If a section is split across multiple chunks, merge it into one comprehensive entry. Do NOT repeat headings.\n"
                    f"Respond in {language}. Do not use emojis. Use Markdown."
                ),
            },
            {
                "role": "user",
                "content": f"Text to analyze:\n\n{text}",
            },
        ],
        max_tokens=4096,
        temperature=0.0,
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
