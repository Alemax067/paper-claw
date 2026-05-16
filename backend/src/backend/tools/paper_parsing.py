from __future__ import annotations

from langchain_core.tools import tool

from backend.services.document_processing import DocumentProcessingService
from backend.services.parsing import ParseChainService
from backend.tools.context import resolve_active_paper_id, tool_session


@tool
def parse_paper(paper_id: int | None = None, run_id: int | None = None) -> dict:
    """Run the parser chain for a paper."""
    with tool_session() as session:
        resolved_paper_id = resolve_active_paper_id(session, paper_id)
        job = ParseChainService(session).run_parse_chain(resolved_paper_id, run_id=run_id)
        return {"parse_job_id": job.id, "status": job.status, "strategy": job.strategy, "error": job.error_message}


@tool
def process_paper_document(paper_id: int | None = None) -> dict:
    """Process the latest parsed document into sections, chunks, and references."""
    with tool_session() as session:
        resolved_paper_id = resolve_active_paper_id(session, paper_id)
        processed = DocumentProcessingService(session).process_latest_parsed_document(resolved_paper_id)
        return {"processed_document_id": processed.id, "paper_id": processed.paper_id, "status": processed.status, "version": processed.version}
