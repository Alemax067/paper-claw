from __future__ import annotations

from langchain_core.tools import tool

from backend.services.embeddings import EmbeddingService
from backend.services.retrieval import RetrievalService
from backend.tools.context import tool_session


@tool
def embed_paper_chunks(paper_id: int, provider_name: str | None = None) -> dict:
    """Generate embeddings for paper chunks missing vectors."""
    with tool_session() as session:
        count = EmbeddingService(session).embed_missing_chunks(paper_id, provider_name=provider_name)
        return {"paper_id": paper_id, "embedded_chunks": count}


@tool
def retrieve_paper_evidence(paper_id: int, query: str, limit: int = 5, provider_name: str | None = None) -> dict:
    """Retrieve evidence chunks for a paper question or report."""
    with tool_session() as session:
        results = RetrievalService(session).retrieve(paper_id, query, limit=limit, provider_name=provider_name)
        return {
            "paper_id": paper_id,
            "chunks": [
                {"chunk_id": item.chunk_id, "score": item.score, "mode": item.retrieval_mode, "content": item.content_text, "metadata": item.metadata}
                for item in results
            ],
        }
