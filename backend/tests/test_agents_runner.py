from __future__ import annotations

from backend.agents.runner import _active_paper_system_info, prepare_agent_message_run
from backend.db.models import Paper, Thread
from backend.schemas import AgentMessageRequest


def test_prepare_agent_message_run_persists_request_active_paper(session):
    paper = Paper(title="Focused Paper", year=2024, authors_json=["Alice", "Bob"])
    thread = Thread(title="Thread")
    session.add_all([paper, thread])
    session.commit()

    prepared = prepare_agent_message_run(session, AgentMessageRequest(thread_id=thread.id, message="Summarize this paper", active_paper_id=paper.id))

    assert prepared.active_paper_id == paper.id
    assert session.get(Thread, thread.id).current_focus_paper_id == paper.id
    assert prepared.active_paper_system_info is not None
    assert f"Active paper is #{paper.id}: Focused Paper" in prepared.active_paper_system_info


def test_prepare_agent_message_run_rejects_unknown_active_paper(session):
    thread = Thread(title="Thread")
    session.add(thread)
    session.commit()

    try:
        prepare_agent_message_run(session, AgentMessageRequest(thread_id=thread.id, message="Summarize", active_paper_id=999))
    except ValueError as exc:
        assert "Paper 999 not found" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_prepare_agent_message_run_falls_back_to_thread_focus(session):
    paper = Paper(title="Existing Focus")
    thread = Thread(title="Thread", current_focus_paper_id=None)
    session.add_all([paper, thread])
    session.flush()
    thread.current_focus_paper_id = paper.id
    session.commit()

    prepared = prepare_agent_message_run(session, AgentMessageRequest(thread_id=thread.id, message="Continue"))

    assert prepared.active_paper_id == paper.id
    assert session.get(Thread, thread.id).current_focus_paper_id == paper.id
    assert prepared.active_paper_system_info is not None
    assert f"Active paper is #{paper.id}: Existing Focus" in prepared.active_paper_system_info


def test_active_paper_system_info_includes_catalog_metadata(session):
    paper = Paper(title="Metadata Paper", year=2025, authors_json=["A", "B", "C", "D", "E", "F"])
    session.add(paper)
    session.commit()

    info = _active_paper_system_info(session, paper.id)

    assert info is not None
    assert f"Active paper is #{paper.id}: Metadata Paper" in info
    assert "Year: 2025." in info
    assert "Authors: A, B, C, D, E." in info
    assert "this paper" in info
