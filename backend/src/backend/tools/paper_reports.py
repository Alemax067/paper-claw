from __future__ import annotations

from langchain_core.tools import tool

from backend.db.types import ReportSourceScope
from backend.services.reports import ReportGenerationService
from backend.tools.context import tool_session


@tool
def generate_paper_report(
    paper_id: int,
    instructions: str | None = None,
    source_scope: str = ReportSourceScope.retrieval.value,
    query: str | None = None,
    provider_name: str | None = None,
) -> dict:
    """Generate an evidence-grounded report for a paper."""
    with tool_session() as session:
        result = ReportGenerationService(session).generate_report(
            paper_id,
            instructions=instructions,
            source_scope=source_scope,
            query=query,
            provider_name=provider_name,
        )
        return result.model_dump()


@tool
def answer_paper_question(paper_id: int, question: str, provider_name: str | None = None) -> dict:
    """Answer a paper question using retrieval-backed report generation."""
    with tool_session() as session:
        result = ReportGenerationService(session).generate_report(
            paper_id,
            instructions=f"Answer this question with evidence citations: {question}",
            query=question,
            provider_name=provider_name,
        )
        return result.model_dump()
