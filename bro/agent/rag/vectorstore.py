"""
Simple FAISS-backed vector store abstraction.

Stores embeddings with associated metadata and supports cosine similarity
search. Provides in-memory index with optional persistence to disk.

@file purpose: Defines a minimal FAISS vector store for RAG
"""

# @file purpose: Defines a minimal FAISS vector store for RAG

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import faiss
import numpy as np


@dataclass
class VectorRecord:
    """Represents a stored vector with its text and optional metadata."""

    text: str
    metadata: Optional[dict]


class FaissIndex:
    """FAISS vector index with cosine similarity and simple persistence.

    The index is based on IndexFlatIP over normalized vectors to approximate
    cosine similarity.
    """

    def __init__(self, embedding_dim: int) -> None:
        self._dim = embedding_dim
        self._index = faiss.IndexFlatIP(embedding_dim)
        self._records: list[VectorRecord] = []

    @property
    def size(self) -> int:
        return len(self._records)

    def add(
        self,
        embeddings: Sequence[Sequence[float]],
        texts: Sequence[str],
        metadatas: Optional[Sequence[Optional[dict]]] = None,
    ) -> None:
        """Add vectors with associated texts and metadata to the index.

        Args:
            embeddings: Sequence of embedding vectors.
            texts: Sequence of texts corresponding to embeddings.
            metadatas: Optional sequence of metadata dicts per text.
        """
        if len(embeddings) != len(texts):
            raise ValueError("embeddings and texts must have the same length")
        if metadatas is not None and len(metadatas) != len(texts):
            raise ValueError("metadatas must have same length as texts when provided")

        matrix = np.array(embeddings, dtype="float32")
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        normalized = matrix / norms
        self._index.add(normalized)

        for i, text in enumerate(texts):
            meta = metadatas[i] if metadatas is not None else None
            self._records.append(VectorRecord(text=text, metadata=meta))

    def search(
        self, query_embedding: Sequence[float], k: int = 5
    ) -> List[Tuple[float, VectorRecord]]:
        """Search the index with a single query embedding.

        Args:
            query_embedding: Embedding vector for the query.
            k: Number of nearest neighbors to return.

        Returns:
            List of (score, VectorRecord) tuples sorted by descending score.
        """
        if self.size == 0:
            return []
        vec = np.array([query_embedding], dtype="float32")
        norm = np.linalg.norm(vec, axis=1, keepdims=True)
        norm[norm == 0] = 1.0
        vec = vec / norm
        scores, indices = self._index.search(vec, min(k, self.size))
        results: list[Tuple[float, VectorRecord]] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            results.append((float(score), self._records[int(idx)]))
        return results

    def save(self, dir_path: str) -> None:
        """Persist index and records to a directory.

        Creates directory if not exists. Writes `index.faiss` and `records.json`.
        """
        os.makedirs(dir_path, exist_ok=True)
        faiss.write_index(self._index, os.path.join(dir_path, "index.faiss"))
        records_path = os.path.join(dir_path, "records.json")
        serializable = [
            {"text": r.text, "metadata": r.metadata if r.metadata is not None else None}
            for r in self._records
        ]
        with open(records_path, "w", encoding="utf-8") as f:
            json.dump(
                {"dim": self._dim, "records": serializable}, f, ensure_ascii=False
            )

    @classmethod
    def load(cls, dir_path: str) -> "FaissIndex":
        """Load index and records from a directory created by `save`."""
        index = faiss.read_index(os.path.join(dir_path, "index.faiss"))
        with open(os.path.join(dir_path, "records.json"), "r", encoding="utf-8") as f:
            payload = json.load(f)
        dim = int(payload.get("dim", index.d))
        inst = cls(dim)
        inst._index = index
        inst._records = [
            VectorRecord(text=r["text"], metadata=r.get("metadata"))
            for r in payload.get("records", [])
        ]
        return inst
