from __future__ import annotations

from types import SimpleNamespace

from pydantic import BaseModel
from langchain.agents.middleware import ModelRequest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage

from backend.agents.checkpointing import _psycopg_connection_string
from backend.agents.main_agent import create_paper_claw_agent
from backend.agents.model import _json_safe, _messages_with_active_paper_info, apply_runtime_model
from backend.agents.subagents import create_paper_claw_subagents
from backend.schemas import PaperClawContext


def test_subagent_names_are_unique():
    subagents = create_paper_claw_subagents()
    names = [subagent["name"] for subagent in subagents]
    assert len(names) == len(set(names))
    assert "paper-search-specialist" in names
    assert "paper-qa-specialist" in names


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


def test_model_middleware_forwards_runtime_context(monkeypatch):
    calls = []

    def fake_init_chat_model(*args, **kwargs):
        calls.append((args, kwargs))
        return "model-instance"

    monkeypatch.setattr("backend.agents.model.init_chat_model", fake_init_chat_model)
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

    assert request.model == "model-instance"
    assert calls[0][0] == ("openai:gpt-4o-mini",)
    assert calls[0][1] == {
        "api_key": "key",
        "base_url": "https://example.test/v1",
        "temperature": 0.3,
        "max_tokens": 123,
        "timeout": 45,
        "max_retries": 4,
        "rate_limiter": "limiter",
    }
