from __future__ import annotations

from langchain_core.tools import tool

from backend.db.models import AgentRun, Paper, Thread
from backend.services.search import PaperSearchService
from backend.tools.context import current_tool_context, resolve_active_paper_id, tool_session


@tool
def search_papers(query: str, thread_id: int | None = None, max_results: int = 10) -> dict:
    """Search local/external paper sources and return a confirmation session."""
    with tool_session() as session:
        context = current_tool_context()
        if thread_id is None:
            thread_id = context.thread_id if context is not None else None
        if thread_id is not None and session.get(Thread, thread_id) is None:
            raise ValueError(f"Thread {thread_id} not found for paper search context")
        run_id = context.run_id if context is not None else None
        if run_id is not None and session.get(AgentRun, run_id) is None:
            raise ValueError(f"Run {run_id} not found for paper search context")
        search_session = PaperSearchService(session).search(query, thread_id=thread_id, run_id=run_id, max_results=max_results)
        return {
            "search_session_id": search_session.id,
            "status": search_session.status,
            "candidates": [
                {"id": candidate.id, "rank": candidate.rank, "source": candidate.source, "title": candidate.title, "paper_id": candidate.paper_id}
                for candidate in search_session.candidates
            ],
        }


@tool
def confirm_paper_candidate(search_session_id: int, candidate_id: int, update_thread_focus: bool = True) -> dict:
    """Confirm a search candidate and upsert it into the paper catalog."""
    with tool_session() as session:
        search_session = PaperSearchService(session).confirm_candidate(search_session_id, candidate_id, update_thread_focus=update_thread_focus)
        return {"search_session_id": search_session.id, "status": search_session.status, "selected_candidate_id": search_session.selected_candidate_id}


@tool
def get_paper(paper_id: int | None = None) -> dict:
    """Return paper catalog metadata, defaulting to the active paper."""
    with tool_session() as session:
        resolved_paper_id = resolve_active_paper_id(session, paper_id)
        paper = session.get(Paper, resolved_paper_id)
        if paper is None:
            return {"error": f"Paper {resolved_paper_id} not found"}
        return {"id": paper.id, "title": paper.title, "abstract": paper.abstract, "year": paper.year, "venue": paper.venue, "authors": paper.authors_json}
