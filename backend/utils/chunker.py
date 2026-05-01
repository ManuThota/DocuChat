"""
backend/utils/chunker.py — Split long text into overlapping chunks for RAG.

Strategy:
  - Split by words (whitespace-delimited tokens)
  - Each chunk = chunk_size words
  - Consecutive chunks overlap by `overlap` words so context is not lost
    at chunk boundaries
"""


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """
    Split text into overlapping word-level chunks.

    Args:
        text:       The full document text.
        chunk_size: Target number of words per chunk.
        overlap:    Number of words shared between consecutive chunks.

    Returns:
        List of text chunk strings.

    Example:
        >>> chunks = chunk_text("word " * 1200, chunk_size=500, overlap=50)
        >>> len(chunks)
        3
    """
    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    step = chunk_size - overlap
    start = 0

    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end])
        if chunk.strip():
            chunks.append(chunk)
        start += step

    return chunks
