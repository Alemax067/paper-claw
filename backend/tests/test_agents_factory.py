from __future__ import annotations

from types import SimpleNamespace

from pydantic import BaseModel
from langchain.agents.middleware import ModelRequest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from backend.agents.checkpointing import _psycopg_connection_string
from backend.agents.main_agent import create_paper_claw_agent
from backend.agents.model import _json_safe, _messages_with_active_paper_info, apply_runtime_model
from backend.agents.subagents import create_paper_claw_subagents
from backend.agents.tool_events import record_tool_event_call
from backend.schemas import PaperClawContext
from backend.tools.context import current_tool_context


def test_subagent_names_are_unique():
    subagents = create_paper_claw_subagents()
    names = [subagent["name"] for subagent in subagents]
    assert len(names) == len(set(names))
    assert names == [
        "paper-discovery-specialist",
        "paper-ingestion-specialist",
        "paper-evidence-specialist",
        "paper-report-specialist",
    ]


def test_subagents_have_explicit_isolated_tools():
    subagents = create_paper_claw_subagents()
    tool_names_by_agent = {
        subagent["name"]: {tool.name for tool in subagent["tools"]}
        for subagent in subagents
    }
    assert tool_names_by_agent["paper-discovery-specialist"] == {"search_papers", "recommend_paper_candidates", "get_paper"}
    assert tool_names_by_agent["paper-ingestion-specialist"] == {
        "get_paper_pipeline_status",
        "list_paper_artifacts",
        "download_arxiv_paper_artifacts",
        "download_paper_pdf_from_url",
        "mark_paper_artifact_upload_required",
        "ingest_paper_document",
    }
    assert tool_names_by_agent["paper-evidence-specialist"] == {"get_paper_pipeline_status", "retrieve_paper_evidence"}
    assert tool_names_by_agent["paper-report-specialist"] == {"get_paper_pipeline_status", "list_paper_reports", "generate_paper_report"}
    assert all("tools" in subagent for subagent in subagents)
    assert all("answer_paper_question" not in names for names in tool_names_by_agent.values())


def test_discovery_prompt_returns_candidates_for_deterministic_confirmation():
    subagent = create_paper_claw_subagents()[0]

    assert "Do not confirm, upsert, or claim that an external candidate is active" in subagent["system_prompt"]
    assert "call recommend_paper_candidates exactly once" in subagent["system_prompt"]
    assert "candidate_found_unconfirmed" in subagent["system_prompt"]
    assert "interrupt_on" not in subagent


def test_ingestion_prompt_prepares_artifacts_and_processes_documents():
    subagent = create_paper_claw_subagents()[1]

    assert "get_paper_pipeline_status(include_metadata=True)" in subagent["system_prompt"]
    assert "extract the arXiv id" in subagent["system_prompt"]
    assert "https://arxiv.org/src/{id}" in subagent["system_prompt"]
    assert "download_paper_pdf_from_url" in subagent["system_prompt"]
    assert "call ingest_paper_document exactly once" in subagent["system_prompt"]
    assert "returns one status: ready, parse_failed, or processing_failed" in subagent["system_prompt"]
    assert "frontend-ready markdown" in subagent["system_prompt"]
    assert "structured PaperReference rows" in subagent["system_prompt"]
    assert "must not be described as retrieval chunks or embedding content" in subagent["system_prompt"]
    assert "waiting_for_user_upload" in subagent["system_prompt"]
    assert "parse_failed" in subagent["system_prompt"]
    assert "processing_failed" in subagent["system_prompt"]


def test_agent_factory_constructs_without_external_model_call():
    agent = create_paper_claw_agent(FakeListChatModel(responses=["ok"]))

    assert hasattr(agent, "invoke")
    assert hasattr(agent, "stream")


def test_checkpoint_connection_string_uses_psycopg_driver_url():
    assert (
        _psycopg_connection_string("postgresql+psycopg://paper_claw:paper_claw@localhost:5432/paper_claw")
        == "postgresql://paper_claw:paper_claw@localhost:5432/paper_claw"
    )


def test_json_safe_serializes_model_classes_without_calling_model_dump():
    class ToolArgs(BaseModel):
        query: str

    assert _json_safe({"args_schema": ToolArgs}) == {"args_schema": "ToolArgs"}


def test_active_paper_system_info_is_inserted_before_latest_user_message():
    request = ModelRequest(
        model=FakeListChatModel(responses=["ok"]),
        messages=[AIMessage(content="previous"), HumanMessage(content="question")],
        runtime=SimpleNamespace(context=PaperClawContext(active_paper_system_info="System info: Active paper is #1.")),
    )

    messages = _messages_with_active_paper_info(request)

    assert [message.type for message in messages] == ["ai", "system", "human"]
    assert messages[1].content == "System info: Active paper is #1."
    assert request.messages == [AIMessage(content="previous"), HumanMessage(content="question")]


def test_tool_middleware_binds_runtime_context():
    seen = []
    request = SimpleNamespace(
        runtime=SimpleNamespace(context=PaperClawContext(thread_id=12, active_paper_id=56)),
        tool_call={"id": "call-1", "args": {}},
        tool=SimpleNamespace(name="fake_tool"),
    )

    def handler(_request):
        seen.append(current_tool_context())
        return ToolMessage(content="ok", tool_call_id="call-1")

    result = record_tool_event_call(request, handler)

    assert isinstance(result, ToolMessage)
    assert seen == [PaperClawContext(thread_id=12, active_paper_id=56)]
    assert current_tool_context() is None


def test_model_middleware_forwards_runtime_context(monkeypatch):
    calls = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr("backend.agents.model.ChatOpenAI", FakeChatOpenAI)
    request = SimpleNamespace(
        runtime=SimpleNamespace(
            context=PaperClawContext(
                model="openai:gpt-4o-mini",
                api_key="key",
                base_url="https://example.test/v1",
                temperature=0.3,
                max_tokens=123,
                timeout=45,
                max_retries=4,
                rate_limiter="limiter",
            )
        ),
        model=None,
    )

    apply_runtime_model(request)

    assert isinstance(request.model, FakeChatOpenAI)
    assert calls[0] == {
        "model": "openai:gpt-4o-mini",
        "api_key": "key",
        "base_url": "https://example.test/v1",
        "temperature": 0.3,
        "max_tokens": 123,
        "timeout": 45,
        "max_retries": 4,
        "rate_limiter": "limiter",
    }
