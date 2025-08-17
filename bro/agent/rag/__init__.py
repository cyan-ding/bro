"""
Minimal RAG (Retrieval-Augmented Generation) utilities for Bro.

This package provides a minimal set of components to ingest text from URLs or
raw strings, chunk it, embed with OpenAI, and store/retrieve with FAISS.

@file purpose: Defines minimal RAG interfaces and helpers
"""

# @file purpose: Defines minimal RAG interfaces and helpers

from .chunk import chunk_text
from .embed import OpenAIEmbedder
from .ingest import extract_text, fetch_and_extract
from .retriever import Retriever
from .vectorstore import FaissIndex

__all__ = [
    "fetch_and_extract",
    "extract_text",
    "chunk_text",
    "OpenAIEmbedder",
    "FaissIndex",
    "Retriever",
]
