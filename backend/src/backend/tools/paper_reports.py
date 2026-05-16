from __future__ import annotations

from langchain_core.tools import tool

from backend.db.types import ReportSourceScope
from backend.services.reports import ReportGenerationService
from backend.tools.context import resolve_active_paper_id, tool_session


@tool
def generate_paper_report(
    instructions: str | None = None,
    source_scope: str = ReportSourceScope.retrieval.value,
    query: str | None = None,
    paper_id: int | None = None,
) -> dict:
    """Generate an evidence-grounded report for a paper."""
    with tool_session() as session:
        resolved_paper_id = resolve_active_paper_id(session, paper_id)
        result = ReportGenerationService(session).generate_report(
            resolved_paper_id,
            instructions=instructions,
            source_scope=source_scope,
            query=query,
        )
        return result.model_dump()
