from __future__ import annotations

from langchain_core.messages import AIMessage

from backend.db.models import AgentRun, Message, Thread
from backend.db.repositories import AgentRunRepository
from backend.db.types import MessageRole, RunStatus, WorkflowName


class FakeAgent:
    def __init__(self, output):
        self.output = output
        self.calls = []

    def invoke(self, payload, *, context):
        self.calls.append((payload, context))
        if isinstance(self.output, Exception):
            raise self.output
        return self.output


def test_post_agent_message_creates_thread_messages_run_and_events(client, session, monkeypatch):
    fake_agent = FakeAgent({"messages": [AIMessage(content="assistant answer")]})
    monkeypatch.setattr("backend.agents.runner.create_paper_claw_agent", lambda: fake_agent)

    response = client.post("/api/agent/messages", json={"message": "Explain this paper", "model": "test-model", "api_key": "secret"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == RunStatus.succeeded.value
    assert payload["message"] == "assistant answer"
    assert fake_agent.calls[0][0]["messages"][0]["content"] == "Explain this paper"
    assert fake_agent.calls[0][1].thread_id == payload["thread_id"]
    assert fake_agent.calls[0][1].run_id == payload["run_id"]
    assert fake_agent.calls[0][1].model == "test-model"
    assert fake_agent.calls[0][1].api_key == "secret"
    run = session.get(AgentRun, payload["run_id"])
    assert run.status == RunStatus.succeeded.value
    assert run.input_json["has_api_key"] is True
    assert "api_key" not in run.input_json
    messages = session.query(Message).filter(Message.thread_id == payload["thread_id"]).order_by(Message.created_at).all()
    assert [message.role for message in messages] == [MessageRole.user.value, MessageRole.assistant.value]
    assert messages[-1].run_id == run.id
    assert [event.event_type for event in run.events] == ["agent_message_received", "agent_message_completed"]


def test_post_agent_message_reuses_existing_thread(client, session, monkeypatch):
    thread = Thread(title="Existing thread")
    session.add(thread)
    session.commit()
    monkeypatch.setattr("backend.agents.runner.create_paper_claw_agent", lambda: FakeAgent({"messages": [AIMessage(content="ok")]}))

    response = client.post("/api/agent/messages", json={"thread_id": thread.id, "message": "Continue"})

    assert response.status_code == 200
    assert response.json()["thread_id"] == thread.id


def test_post_agent_message_failure_marks_run_failed(client, session, monkeypatch):
    monkeypatch.setattr("backend.agents.runner.create_paper_claw_agent", lambda: FakeAgent(RuntimeError("model failed")))

    response = client.post("/api/agent/messages", json={"message": "fail"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == RunStatus.failed.value
    assert payload["error"] == "model failed"
    run = session.get(AgentRun, payload["run_id"])
    assert run.status == RunStatus.failed.value
    assert run.error_message == "model failed"
    assert run.events[-1].event_type == "agent_message_failed"


def test_run_events_endpoint_filters_after_sequence(client, session):
    run = AgentRunRepository(session).create(WorkflowName.paper_qa.value, status=RunStatus.running.value)
    repo = AgentRunRepository(session)
    repo.append_event(run.id, "first")
    repo.append_event(run.id, "second")
    session.commit()

    response = client.get(f"/api/agent/runs/{run.id}/events", params={"after_sequence": 1})

    assert response.status_code == 200
    payload = response.json()
    assert [event["event_type"] for event in payload] == ["second"]


def test_cancel_run_marks_running_run_cancelled(client, session):
    run = AgentRunRepository(session).create(WorkflowName.paper_qa.value, status=RunStatus.running.value)
    session.commit()

    response = client.post(f"/api/agent/runs/{run.id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == RunStatus.cancelled.value
    assert run.events[-1].event_type == "agent_run_cancelled"


def test_route_list_does_not_expose_direct_orchestration_endpoints(client):
    paths = {route.path for route in client.app.routes}

    assert "/api/parse" not in paths
    assert "/api/acquire" not in paths
    assert "/api/reports/generate" not in paths
    assert "/api/search/run" not in paths
