"""
Simple text chunking utilities for RAG.

Splits text into overlapping chunks by character length. Keeps things simple and
deterministic. Token-aware chunking can be added later if needed.

@file purpose: Defines minimal text chunking helpers for RAG
"""

# @file purpose: Defines minimal text chunking helpers for RAG

from __future__ import annotations

from typing import List


def chunk_text(text: str, *, chunk_size: int = 1200, overlap: int = 200) -> List[str]:
    """Split a long string into overlapping chunks.

    Args:
        text: Input text to split.
        chunk_size: Maximum characters per chunk.
        overlap: Number of characters overlapped between consecutive chunks.

    Returns:
        List of chunk strings. Empty list if input is empty.
    """
    if not text:
        return []

    normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not normalized:
        return []

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be in [0, chunk_size)")

    chunks: List[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        chunks.append(normalized[start:end])
        if end == len(normalized):
            break
        start = end - overlap
    return chunks
