"""
Simple retriever combining an embedder and FAISS index.

@file purpose: Defines a minimal retriever interface for querying the store
"""

# @file purpose: Defines a minimal retriever interface for querying the store

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from .embed import OpenAIEmbedder
from .vectorstore import FaissIndex, VectorRecord


@dataclass
class RetrievedDocument:
    """Result item from retrieval."""

    score: float
    text: str
    metadata: dict | None


class Retriever:
    """Combine an embedder and a FAISS index to retrieve relevant chunks."""

    def __init__(self, embedder: OpenAIEmbedder, index: FaissIndex) -> None:
        self._embedder = embedder
        self._index = index

    def query(self, question: str, k: int = 5) -> List[RetrievedDocument]:
        """Retrieve top-k similar chunks for a query string.

        Args:
            question: Natural language query.
            k: Number of results to return.

        Returns:
            List of `RetrievedDocument` with scores and content.
        """
        [embedding] = self._embedder.embed_texts([question])
        results: List[Tuple[float, VectorRecord]] = self._index.search(embedding, k=k)
        return [
            RetrievedDocument(score=s, text=r.text, metadata=r.metadata)
            for s, r in results
        ]
