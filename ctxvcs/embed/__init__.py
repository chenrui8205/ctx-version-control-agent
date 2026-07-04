"""Embedder interface (§1) — no vendor hardcoded at call sites. Write path only."""

from typing import Protocol

from ctxvcs.config import settings


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbedder:
    def __init__(self, model: str | None = None, dim: int | None = None):
        from openai import OpenAI

        cfg = settings()
        self._client = OpenAI()
        self.model = model or cfg.embed_model
        self.dim = dim or cfg.embed_dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = self._client.embeddings.create(model=self.model, input=texts, dimensions=self.dim)
        return [d.embedding for d in resp.data]


def get_embedder() -> Embedder:
    cfg = settings()
    if cfg.embed_provider == "fake":
        from ctxvcs.llm.fakes import FakeEmbedder

        return FakeEmbedder(dim=cfg.embed_dim)
    return OpenAIEmbedder()
