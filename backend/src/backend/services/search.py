from __future__ import annotations

from sqlalchemy.orm import Session

from backend.db.models import SearchCandidate, SearchSession, Thread
from backend.db.repositories import SearchRepository
from backend.db.types import PaperSource, SearchStatus
from backend.integrations.paper_sources import PaperSourceAdapter
from backend.schemas import PaperSearchResult
from backend.services.papers import identifiers_from_search_result, search_papers_by_title, upsert_paper_from_search_result


class PaperSearchService:
    def __init__(self, session: Session, sources: dict[str, PaperSourceAdapter] | None = None) -> None:
        self.session = session
        self.sources = sources or {}

    def search(
        self,
        query: str,
        *,
        thread_id: int | None = None,
        run_id: int | None = None,
        max_results: int = 10,
        source_names: list[str] | None = None,
    ) -> SearchSession:
        search_session = SearchRepository(self.session).create_session(
            query,
            thread_id=thread_id,
            run_id=run_id,
            status=SearchStatus.waiting_for_confirmation.value,
            source_preference=",".join(source_names) if source_names else None,
        )
        candidates = self._local_candidates(query, max_results=max_results)
        for source_name, source in self._selected_sources(source_names).items():
            candidates.extend(source.search(query, max_results=max_results))
        for rank, candidate in enumerate(_dedupe_candidates(candidates)[:max_results], start=1):
            self._add_candidate(search_session.id, rank, candidate)
        if not search_session.candidates:
            search_session.status = SearchStatus.failed.value
        self.session.flush()
        return search_session

    def confirm_candidate(
        self,
        search_session_id: int,
        candidate_id: int,
        *,
        update_thread_focus: bool = True,
    ) -> SearchSession:
        candidate = self.session.get(SearchCandidate, candidate_id)
        if candidate is None or candidate.search_session_id != search_session_id:
            raise ValueError(f"Candidate {candidate_id} does not belong to search session {search_session_id}.")
        paper = candidate.paper or upsert_paper_from_search_result(self.session, _candidate_to_result(candidate))
        candidate.paper_id = paper.id
        search_session = SearchRepository(self.session).confirm_candidate(search_session_id, candidate_id)
        if update_thread_focus and search_session.thread_id is not None:
            thread = self.session.get(Thread, search_session.thread_id)
            if thread is not None:
                thread.current_focus_paper_id = paper.id
        self.session.flush()
        return search_session

    def _local_candidates(self, query: str, *, max_results: int) -> list[PaperSearchResult]:
        papers = search_papers_by_title(self.session, query, limit=max_results)
        return [
            PaperSearchResult(
                source=PaperSource.manual_upload.value,
                source_record_id=f"paper:{paper.id}",
                title=paper.title,
                abstract=paper.abstract,
                authors=list(paper.authors_json or []),
                year=paper.year,
                venue=paper.venue,
                landing_page_url=paper.landing_page_url,
                pdf_url=paper.best_pdf_url,
                score=1.0,
                raw={"paper_id": paper.id, "local": True},
            )
            for paper in papers
        ]

    def _selected_sources(self, source_names: list[str] | None) -> dict[str, PaperSourceAdapter]:
        if source_names is None:
            return self.sources
        return {name: self.sources[name] for name in source_names if name in self.sources}

    def _add_candidate(self, search_session_id: int, rank: int, result: PaperSearchResult) -> SearchCandidate:
        identifiers = identifiers_from_search_result(result)
        paper_id = result.raw.get("paper_id") if result.raw.get("local") else None
        return SearchRepository(self.session).add_candidate(
            search_session_id,
            rank,
            result.source,
            result.title,
            source_record_id=result.source_record_id,
            paper_id=paper_id,
            abstract=result.abstract,
            authors_json=result.authors,
            year=result.year,
            doi=next((item.identifier_value for item in identifiers if item.identifier_type == "doi"), None),
            arxiv_id=next((item.identifier_value for item in identifiers if item.identifier_type == "arxiv"), None),
            openalex_id=next((item.identifier_value for item in identifiers if item.identifier_type == "openalex"), None),
            landing_page_url=result.landing_page_url,
            pdf_url=result.pdf_url,
            score=result.score,
            raw_json=result.raw,
        )


def _candidate_to_result(candidate: SearchCandidate) -> PaperSearchResult:
    return PaperSearchResult(
        source=candidate.source,
        source_record_id=candidate.source_record_id,
        title=candidate.title,
        abstract=candidate.abstract,
        authors=list(candidate.authors_json or []),
        year=candidate.year,
        doi=candidate.doi,
        arxiv_id=candidate.arxiv_id,
        openalex_id=candidate.openalex_id,
        landing_page_url=candidate.landing_page_url,
        pdf_url=candidate.pdf_url,
        score=candidate.score,
        raw=dict(candidate.raw_json or {}),
    )


def _dedupe_candidates(candidates: list[PaperSearchResult]) -> list[PaperSearchResult]:
    seen: set[tuple[str, str]] = set()
    deduped: list[PaperSearchResult] = []
    for candidate in candidates:
        keys = _candidate_keys(candidate)
        if keys and any(key in seen for key in keys):
            continue
        seen.update(keys or [("title", candidate.title.strip().lower())])
        deduped.append(candidate)
    return deduped


def _candidate_keys(candidate: PaperSearchResult) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    for identifier in identifiers_from_search_result(candidate):
        keys.append((identifier.identifier_type, identifier.identifier_value))
    if candidate.source_record_id:
        keys.append((candidate.source, candidate.source_record_id))
    return keys
