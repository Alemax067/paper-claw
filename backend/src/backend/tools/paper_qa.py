from __future__ import annotations

from langchain_core.tools import tool

from backend.services.embeddings import EmbeddingService
from backend.services.retrieval import RetrievalService
from backend.tools.context import resolve_active_paper_id, tool_session


@tool
def embed_paper_chunks(paper_id: int | None = None) -> dict:
    """Generate embeddings for paper chunks missing vectors."""
    with tool_session() as session:
        resolved_paper_id = resolve_active_paper_id(session, paper_id)
        count = EmbeddingService(session).embed_missing_chunks(resolved_paper_id)
        return {"paper_id": resolved_paper_id, "embedded_chunks": count}


@tool
def retrieve_paper_evidence(query: str, paper_id: int | None = None, limit: int = 5) -> dict:
    """Retrieve evidence chunks for a paper question or report."""
    with tool_session() as session:
        resolved_paper_id = resolve_active_paper_id(session, paper_id)
        results = RetrievalService(session).retrieve(resolved_paper_id, query, limit=limit)
        return {
            "paper_id": resolved_paper_id,
            "chunks": [
                {"chunk_id": item.chunk_id, "score": item.score, "mode": item.retrieval_mode, "content": item.content_text, "metadata": item.metadata}
                for item in results
            ],
        }
