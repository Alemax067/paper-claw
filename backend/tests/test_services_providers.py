from __future__ import annotations

import pytest

from backend.db.models import ProviderConfig
from backend.db.types import ProviderKind, ProviderName
from backend.schemas import ProviderResolutionError
from backend.services.providers import resolve_api_key, resolve_provider_config
from backend.settings import REPO_ROOT, Settings


def add_provider(session, **values):
    provider = ProviderConfig(**values)
    session.add(provider)
    session.flush()
    return provider


def test_resolve_default_provider(session):
    add_provider(
        session,
        name="fallback-chat",
        kind=ProviderKind.chat.value,
        provider=ProviderName.openai_compatible.value,
        model="fallback-model",
        is_default=False,
    )
    default = add_provider(
        session,
        name="default-chat",
        kind=ProviderKind.chat.value,
        provider=ProviderName.openai_compatible.value,
        base_url="https://example.invalid/v1",
        model="default-model",
        api_key_ref="env:PAPER_CLAW_TEST_KEY",
        temperature=0.1,
        is_default=True,
        settings_json={"timeout": 30},
    )

    resolved = resolve_provider_config(session, ProviderKind.chat.value)

    assert resolved.id == default.id
    assert resolved.name == "default-chat"
    assert resolved.base_url == "https://example.invalid/v1"
    assert resolved.settings == {"timeout": 30}


def test_resolve_explicit_provider_ignores_other_defaults(session):
    add_provider(
        session,
        name="default-chat",
        kind=ProviderKind.chat.value,
        provider=ProviderName.openai_compatible.value,
        model="default-model",
        is_default=True,
    )
    explicit = add_provider(
        session,
        name="named-chat",
        kind=ProviderKind.chat.value,
        provider=ProviderName.openai_compatible.value,
        model="named-model",
        is_default=False,
    )

    resolved = resolve_provider_config(session, ProviderKind.chat.value, name="named-chat")

    assert resolved.id == explicit.id
    assert resolved.model == "named-model"


def test_resolve_provider_ignores_disabled_configs(session):
    add_provider(
        session,
        name="disabled-chat",
        kind=ProviderKind.chat.value,
        provider=ProviderName.openai_compatible.value,
        enabled=False,
        is_default=True,
    )

    with pytest.raises(ProviderResolutionError) as exc_info:
        resolve_provider_config(session, ProviderKind.chat.value)

    assert exc_info.value.error.code == "provider_not_found"


def test_resolve_api_key_from_env(monkeypatch):
    monkeypatch.setenv("PAPER_CLAW_TEST_KEY", "secret-value")

    assert resolve_api_key("env:PAPER_CLAW_TEST_KEY") == "secret-value"


def test_resolve_api_key_missing_env():
    with pytest.raises(ProviderResolutionError) as exc_info:
        resolve_api_key("env:PAPER_CLAW_MISSING_TEST_KEY")

    assert exc_info.value.error.code == "api_key_missing"


def test_settings_default_storage_root():
    settings = Settings()

    assert REPO_ROOT.name == "paper-claw"
    assert settings.data_dir == REPO_ROOT / "data"
    assert settings.storage_root == REPO_ROOT / "data" / "files"
