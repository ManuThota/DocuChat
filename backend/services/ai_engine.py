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
    Summarize document text using an all-Groq Map-Reduce approach.
    
    Small documents (<18k chars) are processed in one shot.
    Large documents are chunked into 20k-char blocks, summarized via 
    Llama 3-8b-instant (Map), then synthesized by Llama 3.1-70b (Reduce).
    """
    if len(text) < 18000:
        return _groq_summarize(text, mode, language)
        
    # Large document logic (Map-Reduce)
    chunk_size = 20000
    intermediate_summaries = []
    
    # Map Step: Summarize each 20k block using the faster 8B model
    for i in range(0, min(len(text), 300000), chunk_size):
        chunk = text[i:i+chunk_size]
        try:
            summary = _groq_map_summary(chunk, language)
            if summary:
                intermediate_summaries.append(summary)
        except Exception as e:
            print(f"[Summary] Map step failed for chunk {i}: {e}")
            intermediate_summaries.append(chunk[:500] + "...")
            
    combined_text = "\n\n".join(intermediate_summaries)
    
    # Reduce Step: Final high-quality synthesis
    return _groq_summarize(combined_text, mode, language)


def _groq_map_summary(text: str, language: str) -> str:
    """Fast, accurate intermediate summary for large documents."""
    client = _groq_client()
    response = client.chat.completions.create(
        model="llama-3-8b-8192", 
        messages=[
            {
                "role": "system", 
                "content": (
                    f"Summarize the following text segment for a larger document report. "
                    f"Capture the UNIQUE core content, headings, and technical details. "
                    f"IGNORE repetitive page headers, footers, or disclaimer text. "
                    f"Respond in {language}. Do NOT guess or infer sections. ONLY report what is explicitly there."
                )
            },
            {"role": "user", "content": text},
        ],
        max_tokens=1000,
        temperature=0.2,
    )
    return response.choices[0].message.content.strip()


def _groq_summarize(text: str, mode: str, language: str) -> str:
    """Llama 3.1-based summarization via Groq for all modes."""
    client = _groq_client()
    
    instructions = {
        "short":       "Provide a concise 1-2 paragraph summary of the text.",
        "detailed":    "Provide a comprehensive, chapter-by-chapter detailed summary. Merge similar segments into single high-quality sections.",
        "bullet":      "Summarize the text into clear, high-level bullet points. Maintain the original document flow and hierarchy.",
        "executive":   "Write a professional executive summary covering key findings, decisions, and recommendations in chronological order.",
        "study_notes": "Create highly structured study notes. Use bold headings for chapters/sections, define key concepts, and include examples.",
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
                    f"1. **CONSOLIDATION**: If multiple segments discuss the same chapter or topic (e.g. 'Git Configuration' or 'GUI Clients'), you MUST MERGE them into ONE single rich section. Do NOT create 'Continued' sections. Do NOT repeat the same heading.\n"
                    f"2. **NO INFERENCE**: Do NOT guess, 'infer', or imagine content. If a section is mentioned but has no details in the text, SKIP IT. NEVER say 'it can be inferred' or 'this section is not mentioned'. Only report what is EXPLICITLY there.\n"
                    f"3. **HEADINGS**: Use the ACTUAL chapter/section names from the document as ## headers. Do NOT use generic 'Section 1, Section 2' numbering unless that is how the document is written.\n"
                    f"4. **FACTUAL ONLY**: No filler text. No introductory fluff. No 'This chapter covers'. Just the facts from the document.\n"
                    f"Respond in {language}. Do not use emojis."
                ),
            },
            {
                "role": "user",
                "content": f"Document Text:\n\n{text[:100000]}",
            },
        ],
        max_tokens=4096,
        temperature=0.3,
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
