"""
Embedding utilities using OpenAI embeddings API.

Uses `text-embedding-3-small` by default; configurable via constructor.

@file purpose: Defines an embedders interface backed by OpenAI
"""

# @file purpose: Defines an embedders interface backed by OpenAI

from __future__ import annotations

import os
from typing import Iterable, List

from dotenv import load_dotenv
from openai import OpenAI


class OpenAIEmbedder:
    """Thin wrapper around OpenAI embeddings API.

    Args:
        model: Embedding model id. Defaults to `text-embedding-3-small`.
    """

    def __init__(self, model: str = "text-embedding-3-small") -> None:
        load_dotenv()
        api_key = os.environ.get("OPENAI_API_KEY")
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def embed_texts(self, texts: Iterable[str]) -> List[List[float]]:
        """Embed a batch of texts.

        Args:
            texts: Iterable of strings to embed.

        Returns:
            List of vector embeddings (lists of floats), same order as input.
        """
        inputs = [t if t is not None else "" for t in texts]
        if not inputs:
            return []
        response = self._client.embeddings.create(model=self._model, input=inputs)
        return [item.embedding for item in response.data]
