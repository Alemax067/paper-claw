from __future__ import annotations

from langchain_core.tools import tool

from backend.db.models import Paper
from backend.services.search import PaperSearchService
from backend.tools.context import tool_session


@tool
def search_papers(query: str, thread_id: int | None = None, max_results: int = 10) -> dict:
    """Search local/external paper sources and return a confirmation session."""
    with tool_session() as session:
        search_session = PaperSearchService(session).search(query, thread_id=thread_id, max_results=max_results)
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
def get_paper(paper_id: int) -> dict:
    """Return paper catalog metadata."""
    with tool_session() as session:
        paper = session.get(Paper, paper_id)
        if paper is None:
            return {"error": f"Paper {paper_id} not found"}
        return {"id": paper.id, "title": paper.title, "abstract": paper.abstract, "year": paper.year, "venue": paper.venue, "authors": paper.authors_json}
