"""LLM + embedding client wrappers (singletons).

- Chat: DeepSeek via OpenAI-compatible API (LangChain ChatOpenAI).
- Embedding: 阿里通义 text-embedding-v3 via OpenAI-compatible API.
  (DeepSeek 没有 embedding;阿里通义 dashscope 提供 OpenAI 兼容端口,
   1024 维,国内付款,有免费额度。)
"""
from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import SecretStr

from mneme.config import settings


@lru_cache(maxsize=1)
def get_chat_llm(temperature: float = 0.0) -> ChatOpenAI:
    """DeepSeek-chat via OpenAI-compatible API.

    Shared between Awake and Sleep agents.
    """
    return ChatOpenAI(
        model=settings.deepseek_model,
        base_url=settings.deepseek_base_url,
        api_key=SecretStr(settings.deepseek_api_key),
        temperature=temperature,
    )


@lru_cache(maxsize=1)
def get_embedder() -> OpenAIEmbeddings:
    """阿里通义 text-embedding-v3 via OpenAI-compatible API (dashscope).

    Default 1024 dim. Swap base_url + model + dimensions in .env to use
    other providers (OpenAI text-embedding-3-small, BGE-m3 local, etc.).
    """
    return OpenAIEmbeddings(
        model=settings.embed_model,
        api_key=SecretStr(settings.embed_api_key),
        base_url=settings.embed_base_url,
        dimensions=settings.embed_dimensions,
        check_embedding_ctx_length=False,
    )


async def embed_text(text: str) -> list[float]:
    """Single-text embedding helper."""
    return await get_embedder().aembed_query(text)


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch embedding helper."""
    return await get_embedder().aembed_documents(texts)
