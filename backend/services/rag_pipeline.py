"""
backend/services/rag_pipeline.py — Retrieval-Augmented Generation (RAG) pipeline.

How RAG works:
  1. INDEXING (upload time):
     - Document text is split into chunks
     - Each chunk is embedded via the HuggingFace Inference API
       (sentence-transformers/all-MiniLM-L6-v2, 384-dim vectors)
     - Vectors are stored in a local FAISS index (fast, no external DB needed)

  2. RETRIEVAL (query time):
     - User question is embedded with the same model via API
     - FAISS finds the top-k most similar chunks (cosine similarity)
     - Those chunks form the "context" passed to the LLM

  3. GENERATION:
     - Context + question → Flan-T5-large or BART via ai_engine.py

No models are downloaded locally. Only FAISS (index math) runs on-device.
"""

import os
import numpy as np
import faiss
from huggingface_hub import InferenceClient

from backend.utils.chunker import chunk_text
from backend.services.ai_engine import generate_answer, summarize
from backend.config import get_settings

settings = get_settings()

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM   = 384   # all-MiniLM-L6-v2 output dimension


# ─── Embedding via HF API ─────────────────────────────────────────────────────

def _get_client() -> InferenceClient:
    if not settings.hf_api_key:
        raise RuntimeError(
            "HF_API_KEY is not set. Add it to your .env file. "
            "Get a free key at https://huggingface.co/settings/tokens"
        )
    return InferenceClient(token=settings.hf_api_key)


def _embed(texts: list[str]) -> np.ndarray:
    """
    Embed a list of texts using the HF Inference API.

    Returns:
        Float32 numpy array of shape (len(texts), EMBEDDING_DIM).
    """
    try:
        client = _get_client()
        # feature_extraction returns a list[list[float]] or list[list[list[float]]]
        # For sentence-transformers models it returns shape [n_texts, dim]
        raw = client.feature_extraction(texts, model=EMBEDDING_MODEL)
        
        if isinstance(raw, dict) and "error" in raw:
            raise RuntimeError(f"HF API Error: {raw['error']}")
            
        arr = np.array(raw, dtype=np.float32)

        # Some HF endpoints return [n, 1, dim] — squeeze the middle dim if present
        if arr.ndim == 3:
            arr = arr[:, 0, :]
        return arr
    except Exception as exc:
        print(f"[RAG] Embedding failed: {exc}")
        # Return zero vector fallback to prevent complete crash
        return np.zeros((len(texts), EMBEDDING_DIM), dtype=np.float32)


# ─── Indexing ─────────────────────────────────────────────────────────────────

def build_faiss_index(text: str, index_path: str) -> None:
    """
    Chunk document text, embed chunks via HF API, and save FAISS index to disk.

    Args:
        text:       Full extracted document text.
        index_path: File path prefix (without extension) for saving index + chunks.
    """
    chunks = chunk_text(text, chunk_size=500, overlap=50)
    if not chunks:
        raise ValueError("Document has no extractable text to index.")

    print(f"[RAG] Embedding {len(chunks)} chunks via HF API…")

    # Embed in small batches to respect API limits
    BATCH = 32
    embeddings_list = []
    for i in range(0, len(chunks), BATCH):
        batch = chunks[i : i + BATCH]
        embeddings_list.append(_embed(batch))
    embeddings = np.vstack(embeddings_list).astype(np.float32)

    # Normalise for cosine similarity via inner product
    faiss.normalize_L2(embeddings)

    # Build FAISS index
    index = faiss.IndexFlatIP(EMBEDDING_DIM)
    index.add(embeddings)

    # Persist index + raw chunks
    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    faiss.write_index(index, index_path + ".faiss")
    with open(index_path + ".chunks", "w", encoding="utf-8") as f:
        f.write("\n<<<CHUNK>>>\n".join(chunks))

    print(f"[RAG] Indexed {len(chunks)} chunks → {index_path}")


# ─── Retrieval ────────────────────────────────────────────────────────────────

def retrieve_relevant_chunks(query: str, index_path: str, top_k: int = 4) -> list[str]:
    """
    Find the top-k most relevant chunks for a query using FAISS.

    Args:
        query:      The user's question.
        index_path: File path prefix used when building the index.
        top_k:      Number of chunks to retrieve.

    Returns:
        List of relevant text chunk strings.
    """
    faiss_file  = index_path + ".faiss"
    chunks_file = index_path + ".chunks"

    if not os.path.exists(faiss_file):
        return []

    index = faiss.read_index(faiss_file)
    with open(chunks_file, "r", encoding="utf-8") as f:
        chunks = f.read().split("\n<<<CHUNK>>>\n")

    # Embed the query (single text → shape [1, dim])
    query_vec = _embed([query])
    faiss.normalize_L2(query_vec)

    k = min(top_k, index.ntotal)
    _, indices = index.search(query_vec, k)

    return [chunks[i] for i in indices[0] if i < len(chunks)]


# ─── Query Entry Points ───────────────────────────────────────────────────────

def answer_question(
    question: str,
    index_path: str,
    language: str = "English",
) -> str:
    """Full RAG pipeline: embed query → retrieve chunks → generate answer."""
    chunks  = retrieve_relevant_chunks(question, index_path, top_k=4)
    context = "\n\n".join(chunks) if chunks else ""
    return generate_answer(question, context, language=language)


def summarize_document(
    index_path: str,
    mode: str = "short",
    language: str = "English",
) -> str:
    """Summarize a document using its stored indexed chunks."""
    chunks_file = index_path + ".chunks"
    if not os.path.exists(chunks_file):
        return "No indexed document found. Please upload a document first."

    with open(chunks_file, "r", encoding="utf-8") as f:
        chunks = f.read().split("\n<<<CHUNK>>>\n")

    # Use first 6 chunks (BART has ~1024-token input limit)
    text = " ".join(chunks[:6])
    return summarize(text, mode=mode, language=language)
