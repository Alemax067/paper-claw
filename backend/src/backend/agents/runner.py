from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.agents.context import PaperClawContext
from backend.agents.main_agent import create_paper_claw_agent
from backend.api.serializers import run_event_read, run_read
from backend.db.models import AgentRun, AgentRunEvent
from backend.db.repositories import AgentRunRepository, ThreadRepository
from backend.db.types import EventLevel, MessageRole, MessageSource, RunStatus, WorkflowName
from backend.schemas import AgentMessageRequest, AgentMessageResponse, RunEventRead, RunRead


def submit_agent_message(session: Session, request: AgentMessageRequest) -> AgentMessageResponse:
    threads = ThreadRepository(session)
    runs = AgentRunRepository(session)
    thread = threads.get(request.thread_id) if request.thread_id is not None else None
    if request.thread_id is not None and thread is None:
        raise ValueError("Thread not found")
    if thread is None:
        thread = threads.create(_thread_title(request.message))
    threads.add_message(thread.id, MessageRole.user.value, request.message, source=MessageSource.human.value)
    run = runs.create(
        WorkflowName.paper_qa.value,
        thread_id=thread.id,
        status=RunStatus.running.value,
        started_at=datetime.now().astimezone(),
        input_json=_run_input(request),
    )
    runs.append_event(run.id, "agent_message_received", payload_json={"thread_id": thread.id})
    session.commit()

    try:
        output = _invoke_agent(thread.id, run.id, request)
        message_text = _assistant_text(output)
        assistant_message = threads.add_message(
            thread.id,
            MessageRole.assistant.value,
            message_text,
            source=MessageSource.agent.value,
            run_id=run.id,
        )
        run.status = RunStatus.succeeded.value
        run.output_json = _json_object(output)
        run.finished_at = datetime.now().astimezone()
        runs.append_event(run.id, "agent_message_completed", payload_json={"assistant_message_id": assistant_message.id})
        session.flush()
        return AgentMessageResponse(
            thread_id=thread.id,
            run_id=run.id,
            assistant_message_id=assistant_message.id,
            status=run.status,
            message=message_text,
        )
    except Exception as exc:
        run.status = RunStatus.failed.value
        run.error_message = str(exc)
        run.finished_at = datetime.now().astimezone()
        runs.append_event(run.id, "agent_message_failed", level=EventLevel.error.value, payload_json={"error": str(exc)})
        session.flush()
        return AgentMessageResponse(thread_id=thread.id, run_id=run.id, status=run.status, error=str(exc))


def list_run_events(session: Session, run_id: int, after_sequence: int | None = None) -> list[RunEventRead]:
    if session.get(AgentRun, run_id) is None:
        raise ValueError("Run not found")
    statement = select(AgentRunEvent).where(AgentRunEvent.run_id == run_id)
    if after_sequence is not None:
        statement = statement.where(AgentRunEvent.sequence > after_sequence)
    events = session.scalars(statement.order_by(AgentRunEvent.sequence)).all()
    return [run_event_read(event) for event in events]


def cancel_run(session: Session, run_id: int) -> RunRead:
    run = session.get(AgentRun, run_id)
    if run is None:
        raise ValueError("Run not found")
    if run.status in {RunStatus.pending.value, RunStatus.running.value, RunStatus.waiting_for_user.value}:
        run.status = RunStatus.cancelled.value
        run.finished_at = datetime.now().astimezone()
        AgentRunRepository(session).append_event(run.id, "agent_run_cancelled")
        session.flush()
    return run_read(run)


def _invoke_agent(thread_id: int, run_id: int, request: AgentMessageRequest) -> Any:
    agent = create_paper_claw_agent()
    context = PaperClawContext(
        thread_id=thread_id,
        run_id=run_id,
        active_paper_id=request.active_paper_id,
        model=request.model,
        api_key=request.api_key,
        base_url=request.base_url,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        timeout=request.timeout,
        max_retries=request.max_retries,
        chat_provider_name=request.chat_provider_name,
    )
    return agent.invoke({"messages": [{"role": "user", "content": request.message}]}, context=context)


def _thread_title(message: str) -> str:
    title = " ".join(message.strip().split())[:80]
    return title or "New thread"


def _run_input(request: AgentMessageRequest) -> dict[str, Any]:
    data = request.model_dump(exclude={"api_key"})
    data["has_api_key"] = request.api_key is not None
    return data


def _assistant_text(output: Any) -> str:
    if isinstance(output, dict) and "messages" in output:
        for message in reversed(output["messages"]):
            content = _message_content(message)
            if content:
                return content
    content = _message_content(output)
    return content or ""


def _message_content(message: Any) -> str | None:
    if isinstance(message, dict):
        content = message.get("content")
    else:
        content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    return None


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return _json_safe(value)
    return {"result": _json_safe(value)}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump())
    content = getattr(value, "content", None)
    if content is not None:
        return {"content": _json_safe(content)}
    return str(value)
