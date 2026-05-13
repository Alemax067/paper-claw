from __future__ import annotations

from backend.db.models import SearchCandidate, SearchSession, Thread
from backend.db.repositories import AgentRunRepository
from backend.db.types import RunStatus, SearchStatus, WorkflowName


def test_confirm_search_candidate_updates_status_focus_and_event(client, session):
    thread = Thread(title="Confirm thread")
    session.add(thread)
    session.flush()
    run = AgentRunRepository(session).create(WorkflowName.search_confirmation.value, thread_id=thread.id, status=RunStatus.waiting_for_user.value)
    search_session = SearchSession(query_text="paper", thread_id=thread.id, run_id=run.id, status=SearchStatus.waiting_for_confirmation.value)
    session.add(search_session)
    session.flush()
    candidate = SearchCandidate(search_session_id=search_session.id, rank=1, source="arxiv", title="Confirmed", arxiv_id="2401.00001", created_at=__import__("datetime").datetime.now().astimezone())
    session.add(candidate)
    session.commit()

    response = client.post(f"/api/search-sessions/{search_session.id}/confirm", json={"candidate_id": candidate.id})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == SearchStatus.confirmed.value
    assert payload["selected_candidate_id"] == candidate.id
    assert session.get(Thread, thread.id).current_focus_paper_id is not None
    assert run.events[-1].event_type == "search_candidate_confirmed"


def test_reject_search_session_marks_rejected_and_appends_event(client, session):
    run = AgentRunRepository(session).create(WorkflowName.search_confirmation.value, status=RunStatus.waiting_for_user.value)
    search_session = SearchSession(query_text="paper", run_id=run.id, status=SearchStatus.waiting_for_confirmation.value)
    session.add(search_session)
    session.commit()

    response = client.post(f"/api/search-sessions/{search_session.id}/reject", json={"reason": "wrong paper"})

    assert response.status_code == 200
    assert response.json()["status"] == SearchStatus.rejected.value
    assert run.events[-1].event_type == "search_session_rejected"
    assert run.events[-1].payload_json["reason"] == "wrong paper"


def test_approval_cancel_updates_run(client, session):
    run = AgentRunRepository(session).create(WorkflowName.analysis_report.value, status=RunStatus.running.value)
    session.commit()

    response = client.post(f"/api/agent/runs/{run.id}/approval", json={"decision": "cancel", "comment": "stop"})

    assert response.status_code == 200
    assert response.json()["status"] == RunStatus.cancelled.value
    assert run.events[-1].event_type == "approval_decision"
