from __future__ import annotations

from backend.db.models import Paper, SearchCandidate, Thread
from backend.db.types import SearchStatus
from backend.schemas import PaperSearchResult
from backend.services.search import PaperSearchService


class FakeSource:
    def __init__(self, results: list[PaperSearchResult]) -> None:
        self.results = results
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, max_results: int = 10) -> list[PaperSearchResult]:
        self.calls.append((query, max_results))
        return self.results


def test_search_session_persists_local_and_external_candidates(session):
    session.add(Paper(title="Local RAG Paper", abstract="local"))
    session.commit()
    external = FakeSource([
        PaperSearchResult(
            source="arxiv",
            source_record_id="2401.00001",
            title="External RAG Paper",
            arxiv_id="2401.00001",
        )
    ])

    search_session = PaperSearchService(session, {"arxiv": external}).search("RAG Paper", max_results=10)

    assert search_session.status == SearchStatus.waiting_for_confirmation.value
    assert [candidate.title for candidate in search_session.candidates] == ["Local RAG Paper", "External RAG Paper"]
    assert external.calls == [("RAG Paper", 10)]


def test_search_deduplicates_candidates_by_identifier(session):
    duplicated = PaperSearchResult(
        source="arxiv",
        source_record_id="2401.00001",
        title="Duplicate",
        arxiv_id="2401.00001v1",
    )
    source = FakeSource([duplicated, duplicated.model_copy(update={"arxiv_id": "2401.00001v2"})])

    search_session = PaperSearchService(session, {"arxiv": source}).search("duplicate")

    assert len(search_session.candidates) == 1


def test_confirm_candidate_upserts_paper_and_updates_thread_focus(session):
    thread = Thread(title="Search thread")
    session.add(thread)
    session.commit()
    result = PaperSearchResult(
        source="openalex",
        source_record_id="https://openalex.org/W1",
        title="Confirmed Paper",
        doi="10.1000/confirmed",
        openalex_id="https://openalex.org/W1",
        authors=["A"],
    )
    search_service = PaperSearchService(session, {"openalex": FakeSource([result])})
    search_session = search_service.search("confirmed", thread_id=thread.id)
    candidate = search_session.candidates[0]

    confirmed = search_service.confirm_candidate(search_session.id, candidate.id)

    assert confirmed.status == SearchStatus.confirmed.value
    assert confirmed.selected_candidate_id == candidate.id
    assert candidate.paper_id is not None
    assert session.get(Thread, thread.id).current_focus_paper_id == candidate.paper_id


def test_confirm_candidate_can_skip_thread_focus_update(session):
    thread = Thread(title="Search thread")
    session.add(thread)
    session.commit()
    result = PaperSearchResult(source="arxiv", source_record_id="2401.00001", title="Paper", arxiv_id="2401.00001")
    search_service = PaperSearchService(session, {"arxiv": FakeSource([result])})
    search_session = search_service.search("paper", thread_id=thread.id)
    candidate = search_session.candidates[0]

    search_service.confirm_candidate(search_session.id, candidate.id, update_thread_focus=False)

    assert session.get(Thread, thread.id).current_focus_paper_id is None


def test_confirm_candidate_rejects_candidate_from_other_session(session):
    service = PaperSearchService(session)
    first = service.search("one")
    second = service.search("two")
    candidate = SearchCandidate(search_session_id=second.id, rank=1, source="manual_upload", title="Wrong", created_at=__import__("datetime").datetime.now().astimezone())
    session.add(candidate)
    session.commit()

    try:
        service.confirm_candidate(first.id, candidate.id)
    except ValueError as exc:
        assert "does not belong" in str(exc)
    else:
        raise AssertionError("expected ValueError")
