"""Minimal chat-completion client: local OpenAI-compatible server or any litellm model."""

import os
import time
from typing import List, Optional

import litellm
from openai import AsyncOpenAI
from pydantic import BaseModel

LOCAL_PREFIX = "local/"
LOCAL_BASE_URL = os.environ.get("BRO_LOCAL_BASE_URL", "http://127.0.0.1:8080/v1")


class Completion(BaseModel):
    text: str
    prompt_tokens: int = 0
    cached_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0


class ChatModel:
    def __init__(self, model: str, max_tokens: int = 160, temperature: float = 0.0):
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._local: Optional[AsyncOpenAI] = None
        if model.startswith(LOCAL_PREFIX):
            self._local = AsyncOpenAI(base_url=LOCAL_BASE_URL, api_key="local")

    @property
    def is_local(self) -> bool:
        return self._local is not None

    async def complete(self, system: str, user: str, stop: Optional[List[str]] = None) -> Completion:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        started = time.perf_counter()
        if self._local:
            response = await self._local.chat.completions.create(
                model=self.model[len(LOCAL_PREFIX) :],
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                stop=stop,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
        else:
            response = await litellm.acompletion(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                stop=stop,
            )
        latency_ms = int((time.perf_counter() - started) * 1000)
        usage = getattr(response, "usage", None)
        details = getattr(usage, "prompt_tokens_details", None) if usage else None
        cached = getattr(details, "cached_tokens", 0) if details else 0
        return Completion(
            text=response.choices[0].message.content or "",
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            cached_tokens=cached or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            latency_ms=latency_ms,
        )
