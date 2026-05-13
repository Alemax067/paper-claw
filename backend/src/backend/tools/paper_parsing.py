from __future__ import annotations

from langchain_core.tools import tool

from backend.services.document_processing import DocumentProcessingService
from backend.services.parsing import ParseChainService
from backend.tools.context import tool_session


@tool
def parse_paper(paper_id: int, run_id: int | None = None) -> dict:
    """Run the parser chain for a paper."""
    with tool_session() as session:
        job = ParseChainService(session).run_parse_chain(paper_id, run_id=run_id)
        return {"parse_job_id": job.id, "status": job.status, "strategy": job.strategy, "error": job.error_message}


@tool
def process_paper_document(paper_id: int) -> dict:
    """Process the latest parsed document into sections, chunks, and references."""
    with tool_session() as session:
        processed = DocumentProcessingService(session).process_latest_parsed_document(paper_id)
        return {"processed_document_id": processed.id, "paper_id": processed.paper_id, "status": processed.status, "version": processed.version}
