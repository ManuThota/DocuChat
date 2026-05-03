"""
backend/services/ai_engine.py — AI inference wrappers.

Architecture (three-model routing by task):
  ┌──────────────────────────────────────────────────────────────────────────┐
  │ Task                    │ Provider  │ Model                              │
  │─────────────────────────│───────────│────────────────────────────────────│
  │ Q&A / Chat              │ Groq API  │ llama-3.1-8b-instant   (6k TPM)   │
  │ Map phase (per-chunk)   │ Groq API  │ llama-3.1-8b-instant   (6k TPM)   │
  │ Summary synthesis       │ Groq API  │ llama-3.3-70b-versatile (6k TPM)  │
  │ Map-phase fallback      │ HuggingFace│ facebook/bart-large-cnn           │
  │ Embeddings (RAG)        │ HuggingFace│ sentence-transformers/            │
  │                         │ Inference │   all-MiniLM-L6-v2                │
  └──────────────────────────────────────────────────────────────────────────┘

Summarization Pipeline (paragraph-aware Map-Reduce):
  1. MAP   — Split document on paragraph boundaries (\\n\\n) into ~4000-char
             chunks. Each chunk is sent to llama-3.1-8b-instant to extract
             headings + 1-sentence descriptions. HF BART is the silent
             fallback if Groq is busy.
  2. REDUCE — All mini-summaries are joined and sent to llama-3.3-70b-versatile
              for final synthesis in the requested mode (short / detailed /
              bullet / executive / study_notes).

Q&A Pipeline:
  - Top relevant FAISS chunks are retrieved and passed as context (≤5000 chars).
  - llama-3.1-8b-instant answers grounded in the document context.
  - If the topic is not in the document, the model answers from general knowledge.

API keys (free tiers):
  Groq  → https://console.groq.com/keys          (add GROQ_API_KEY to .env)
  HF    → https://huggingface.co/settings/tokens  (add HF_API_KEY to .env)
"""

from __future__ import annotations

import time
from groq import Groq
from huggingface_hub import InferenceClient

from backend.config import get_settings

settings = get_settings()

# ─── Model identifiers ────────────────────────────────────────────────────────
# Small/fast model — 6,000 TPM free. Used for Q&A chat.
GROQ_CHAT_MODEL  = "llama-3.1-8b-instant"
# High-quality 70B model — for final summary synthesis.
GROQ_SUM_MODEL   = "llama-3.3-70b-versatile"
# Fast map-phase model — reuses the chat model (llama3-8b-8192 is decommissioned).
GROQ_MINI_MODEL  = "llama-3.1-8b-instant"
# HuggingFace BART — used as silent fallback for map phase.
HF_SUMMARY_MODEL = "facebook/bart-large-cnn"


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
            f"You are an expert document assistant. Answer in {language}.\n"
            f"RULES:\n"
            f"1. **DEPTH FIRST**: For any specific topic, give an exhaustive, in-depth answer. "
            f"Cover every detail, sub-point, step, command, and example present in the document about that topic. "
            f"Do NOT give a vague overview when detailed info is available.\n"
            f"2. **GROUNDED**: Base answers on the DOCUMENT CONTEXT. "
            f"If a topic is not in the document, say so briefly then answer from general knowledge.\n"
            f"3. **FORMATTING**: Use **bold** for key terms, *italics* for definitions, "
            f"### headers for major sub-topics, numbered/bullet lists for steps, "
            f"and ```code``` blocks for ALL commands and code.\n"
            f"4. **EXAMPLES**: Include every example, command, and syntax from the document relevant to the question.\n"
            f"5. **DIRECT**: Begin the answer immediately. No preambles like 'Based on the context'.\n"
            f"6. **NO EMOJIS**. Markdown only."
        )
        user_content = (
            f"DOCUMENT CONTEXT:\n{context[:5000]}\n\n"
            f"QUESTION: {question}"
        )
    else:
        system_content = (
            f"You are a helpful AI assistant. Answer clearly and concisely in {language}. "
            f"Do not use emojis. Use Markdown formatting."
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
    Summarize a document using a paragraph-aware Map-Reduce pipeline.
    Always runs map-reduce so raw document text never reaches the reduce model.
    """
    # Tiny documents only: summarize the raw text directly (no sections to map)
    if len(text) <= 2000:
        return _groq_summarize(text, mode, language)

    # Split on paragraph boundaries to preserve section integrity
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    # --- MAP PHASE ---
    # Maximize coverage per call: 15,000 chars ≈ 3,750 tokens.
    # Total per call (3.7k input + 0.4k output) = 4.1k tokens. Safe for 6k TPM.
    num_target_chunks = 40
    chunk_size_chars = min(15000, max(3000, len(text) // num_target_chunks))
    
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for para in paragraphs:
        if current_len + len(para) > chunk_size_chars and current:
            chunks.append("\n\n".join(current))
            current, current_len = [], 0
        current.append(para)
        current_len += len(para)
    if current:
        chunks.append("\n\n".join(current))

    # Safety cap: 100 chunks covers up to 1.5 million characters (~400,000 words).
    chunks = chunks[:100]

    intermediate_summaries: list[str] = []
    use_hf_only = False # Flag to switch to HF if Groq hits rate limits
    
    for idx, chunk in enumerate(chunks):
        try:
            s = ""
            if not use_hf_only:
                # Delay to avoid hitting Groq's burst TPM limit
                if idx > 0: time.sleep(1.8)
                
                try:
                    s = _groq_mini_summary(chunk, language)
                except Exception as e:
                    if "413" in str(e) or "429" in str(e):
                        print(f"[AI] Groq TPM hit, switching to HF for remaining chunks.")
                        use_hf_only = True
                    else:
                        raise e
            
            if not s:
                # Fallback to HF BART (no 6k TPM limit)
                s = _hf_fast_summary(chunk[:4000])
                
            if s:
                intermediate_summaries.append(s)
        except Exception as e:
            print(f"[AI] Chunk {idx} map failed: {e}")

    # --- REDUCE PHASE ---
    if not intermediate_summaries:
        combined = text[:5000]  # last resort
    else:
        combined = "\n".join(intermediate_summaries)

    # detailed/study_notes get a larger budget to cover all sections
    combined_limit = 9000 if mode in ("detailed", "study_notes") else 4000
    return _groq_summarize(combined[:combined_limit], mode, language)


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
    """
    Map-phase: extract ONLY heading names + a max-10-word description.
    """
    try:
        # Final safety check: if chunk is somehow huge, truncate to 18k chars (~4.5k tokens)
        safe_text = text[:18000]
        
        client = _groq_client()
        response = client.chat.completions.create(
            model=GROQ_MINI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are an index extractor. "
                        f"For every chapter or section heading you find in the text, "
                        f"output exactly ONE line in this format: "
                        f"'[Heading name]: [max 8 words describing the topic]' "
                        f"Example: '1.3 What is a Container?: Defines lightweight isolated runtime environments.' "
                        f"Rules: output ONLY these one-line entries. No paragraphs. No extra text. "
                        f"Do NOT copy sentences from the document. Respond in {language}."
                    )
                },
                {"role": "user", "content": safe_text}
            ],
            max_tokens=400,
            temperature=0.0,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[Mini] {e}")
        return ""


def _groq_summarize(text: str, mode: str, language: str) -> str:
    """Final Reduce phase — synthesizes mini-summaries into the requested format."""
    client = _groq_client()

    if not text.strip():
        return "The document appears to be empty or unreadable."

    mode_instructions = {
        "short": "Write a concise 2-3 paragraph summary of the document's main purpose, key topics, and conclusions.",
        "detailed": (
            "Create a structured chapter-by-chapter overview of the document. "
            "Format EXACTLY like this:\n"
            "## 1. Chapter Title\n"
            "- Brief overview of this chapter (1 sentence).\n"
            "\n"
            "### 1.1 Sub-section Title\n"
            "- What this sub-section covers (1-2 bullet points, concise).\n"
            "\n"
            "## 2. Next Chapter\n"
            "- Brief overview.\n"
            "\n"
            "STRICT RULES:\n"
            "- Cover EVERY chapter and sub-section in order. Do NOT skip any.\n"
            "- Use bullet points ONLY — no long paragraphs.\n"
            "- Keep each bullet concise (max 20 words).\n"
            "- Complete the ENTIRE document. Do not stop early."
        ),
        "bullet": "Summarize into grouped bullet points. Use **bold** for key terms and ### headers for each major topic.",
        "executive": "Write a professional executive summary: a 1-paragraph overview, bold bullet points for key findings, and a Conclusion.",
        "study_notes": (
            "Create structured study notes covering the ENTIRE document. "
            "Format EXACTLY like this:\n"
            "## Topic / Chapter Name\n"
            "- **Key concept**: 1-sentence explanation.\n"
            "- **Another concept**: 1-sentence explanation.\n"
            "\n"
            "### Sub-topic Name\n"
            "- **Term**: definition or explanation (concise).\n"
            "\n"
            "STRICT RULES:\n"
            "- Cover EVERY chapter and sub-section in order. Do NOT skip any.\n"
            "- Use **bold** for all key terms and definitions.\n"
            "- Bullet points only — no long paragraphs.\n"
            "- Include commands/code in ```code``` blocks where relevant.\n"
            "- Complete the ENTIRE document. Do not stop early."
        ),
    }
    instruction = mode_instructions.get(mode, "Summarize the following document.")

    # Give detailed mode more token budget to avoid mid-document truncation
    max_tok = 5000 if mode in ("detailed", "study_notes") else 1500
    max_tok_fallback = 3000 if mode in ("detailed", "study_notes") else 900

    system_prompt = f"""You are a professional document analyst.

Your task: {instruction}

STRICT ARCHITECTURAL RULES:
1. **NO VERBATIM COPYING**: Never reproduce source sentences. Write fresh, high-level overviews.
2. **HEADING STRUCTURE**: You MUST use `##` for Chapters and `###` for Sub-sections. This is non-negotiable.
3. **FULL COVERAGE**: You are given an INDEX of the entire document. You must process EVERY section in that index.
4. **NO TRUNCATION**: Your response must be complete and cover the last section of the index.
5. **BULLETS ONLY**: Use concise bullet points for descriptions (max 20 words per bullet).

Respond in {language}. Use Markdown. No emojis."""

    # Calculate approximate tokens to respect Groq's 6000 TPM limit
    # input_chars // 4 is a safe heuristic for tokens
    input_tokens = len(text) // 4
    
    # If the input itself is too large for the 6k limit, truncate it
    if input_tokens > 4500:
        text = text[:18000] # Cap input at ~4500 tokens
        input_tokens = len(text) // 4

    # max_tokens + input_tokens must be < 6000
    safe_max_tok = min(max_tok, 5800 - input_tokens)
    if safe_max_tok < 500:
        safe_max_tok = 500 # minimum viable response
    
    # Split-Synthesis for long detailed summaries to bypass 6k TPM limit
    # If the index is large and we need a detailed output, do it in two passes
    if mode in ("detailed", "study_notes") and input_tokens > 2000:
        lines = text.split("\n")
        mid = len(lines) // 2
        part1 = "\n".join(lines[:mid])
        part2 = "\n".join(lines[mid:])
        
        results = []
        for i, part in enumerate([part1, part2]):
            # Recalculate tokens for this part
            p_tokens = len(part) // 4
            p_max = min(3000, 5800 - p_tokens)
            
            try:
                # Add a small delay between parts to reset TPM window if needed
                if i > 0: time.sleep(2)
                
                res = client.chat.completions.create(
                    model=GROQ_SUM_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": f"Document content (Part {i+1}):\n\n{part}"},
                    ],
                    max_tokens=int(p_max),
                    temperature=0.0,
                )
                results.append(res.choices[0].message.content.strip())
            except Exception as e:
                print(f"[SplitSum] Part {i+1} failed: {e}")
        
        if results:
            return "\n\n".join(results)
            
    # Default single-pass synthesis
    try:
        response = client.chat.completions.create(
            model=GROQ_SUM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": f"Document content:\n\n{text}"},
            ],
            max_tokens=int(safe_max_tok),
            temperature=0.0,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[Sum] {GROQ_SUM_MODEL} failed ({e}), falling back to {GROQ_CHAT_MODEL}")
        
        # Recalculate for fallback model which might have different limits (usually same 6k)
        text_fallback = text[:6000] # Much smaller context for fallback
        input_tokens_fb = len(text_fallback) // 4
        safe_max_fb = min(max_tok_fallback, 5800 - input_tokens_fb)
        
        response = client.chat.completions.create(
            model=GROQ_CHAT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": f"Document content:\n\n{text_fallback}"},
            ],
            max_tokens=int(safe_max_fb),
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
