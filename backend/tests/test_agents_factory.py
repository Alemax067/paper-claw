from __future__ import annotations

from types import SimpleNamespace

from langchain_core.language_models.fake_chat_models import FakeListChatModel

from backend.agents.main_agent import create_paper_claw_agent
from backend.agents.model import apply_runtime_model
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
