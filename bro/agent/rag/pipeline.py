"""
End-to-end minimal RAG pipeline helpers.

Provides `ingest_urls` to create/update a FAISS index from pages, and
`answer_with_context` to fetch top-k contexts for a question. This module does
not call an LLM; it returns retrieved contexts so the caller can compose the
final prompt with their preferred model.

@file purpose: Defines minimal end-to-end helpers for the RAG flow
"""

# @file purpose: Defines minimal end-to-end helpers for the RAG flow

from __future__ import annotations

from typing import List

from playwright.async_api import Page

from .chunk import chunk_text
from .embed import OpenAIEmbedder
from .ingest import fetch_and_extract
from .retriever import RetrievedDocument, Retriever
from .vectorstore import FaissIndex


async def ingest_page(
    page: Page,
    *,
    embed_model: str = "text-embedding-3-small",
    chunk_size: int = 1200,
    overlap: int = 200,
) -> FaissIndex:
    """Fetch each URL, extract text, chunk, embed, and build a FAISS index.

    Args:
        urls: Iterable of page URLs.
        embed_model: OpenAI embedding model name.
        chunk_size: Chunk size in characters.
        overlap: Overlap in characters between chunks.

    Returns:
        A populated `FaissIndex`.
    """
    embedder = OpenAIEmbedder(model=embed_model)

    # Quick probe to get embedding dimension without an extra call: embed one token
    probe_vec = embedder.embed_texts(["probe"])[0]
    index = FaissIndex(embedding_dim=len(probe_vec))

    texts: List[str] = []
    metadatas: List[dict] = []

    extracted = await fetch_and_extract(page)
    if not extracted:
        return index
    chunks = chunk_text(extracted, chunk_size=chunk_size, overlap=overlap)
    for c in chunks:
        texts.append(c)
        metadatas.append({"source": page.url})

    if not texts:
        return index

    embeddings = embedder.embed_texts(texts)
    index.add(embeddings, texts, metadatas)
    return index


def answer_with_context(
    question: str,
    index: FaissIndex,
    *,
    embed_model: str = "text-embedding-3-small",
    k: int = 5,
) -> List[RetrievedDocument]:
    """Retrieve top-k contexts for a question using the provided index.

    Args:
        question: The natural language question.
        index: A previously built `FaissIndex`.
        embed_model: OpenAI embedding model to use.
        k: Number of results to return.

    Returns:
        List of retrieved documents to be used to build an LLM prompt.
    """
    retriever = Retriever(OpenAIEmbedder(model=embed_model), index)
    return retriever.query(question, k=k)
