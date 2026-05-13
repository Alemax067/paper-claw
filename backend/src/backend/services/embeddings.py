from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import DocumentChunk, ProcessedDocument
from backend.db.types import ProviderKind
from backend.integrations.embeddings import EmbeddingAdapter, FixtureEmbeddingAdapter, OpenAICompatibleEmbeddingAdapter
from backend.schemas import ResolvedProviderConfig
from backend.services.providers import resolve_provider_config


class EmbeddingService:
    def __init__(self, session: Session, adapters: dict[str, EmbeddingAdapter] | None = None) -> None:
        self.session = session
        self.adapters = adapters or {
            "fixture": FixtureEmbeddingAdapter(),
            "openai_compatible": OpenAICompatibleEmbeddingAdapter(),
            "openai": OpenAICompatibleEmbeddingAdapter(),
        }

    def embed_missing_chunks(self, paper_id: int, *, provider_name: str | None = None, batch_size: int = 64) -> int:
        provider = resolve_provider_config(self.session, ProviderKind.embedding.value, provider_name)
        adapter = self._adapter_for(provider)
        chunks = list(
            self.session.scalars(
                select(DocumentChunk)
                .join(ProcessedDocument)
                .where(
                    ProcessedDocument.paper_id == paper_id,
                    DocumentChunk.embedding.is_(None),
                )
                .order_by(DocumentChunk.chunk_index)
            )
        )
        embedded = 0
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            vectors = adapter.embed_texts(provider, [chunk.content_text for chunk in batch])
            for chunk, vector in zip(batch, vectors, strict=True):
                chunk.embedding = vector
                chunk.embedding_model = provider.model or provider.name
                chunk.embedding_dimension = len(vector)
                embedded += 1
        self.session.flush()
        return embedded

    def embed_query(self, query: str, *, provider_name: str | None = None) -> tuple[list[float], ResolvedProviderConfig]:
        provider = resolve_provider_config(self.session, ProviderKind.embedding.value, provider_name)
        vector = self._adapter_for(provider).embed_texts(provider, [query])[0]
        return vector, provider

    def _adapter_for(self, provider: ResolvedProviderConfig) -> EmbeddingAdapter:
        adapter = self.adapters.get(provider.provider)
        if adapter is None:
            raise ValueError(f"No embedding adapter configured for provider {provider.provider!r}.")
        return adapter
