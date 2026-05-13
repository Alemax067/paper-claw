from __future__ import annotations

import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import ProviderConfig
from backend.schemas import ProviderResolutionError, ResolvedProviderConfig


def resolve_provider_config(session: Session, kind: str, name: str | None = None) -> ResolvedProviderConfig:
    statement = select(ProviderConfig).where(ProviderConfig.kind == kind, ProviderConfig.enabled.is_(True))
    if name is not None:
        statement = statement.where(ProviderConfig.name == name)
        provider_config = session.scalar(statement)
        if provider_config is None:
            raise ProviderResolutionError(
                "provider_not_found",
                f"No enabled provider config named {name!r} for kind {kind!r}.",
                {"kind": kind, "name": name},
            )
        return _to_resolved_provider(provider_config)

    default_statement = statement.where(ProviderConfig.is_default.is_(True)).order_by(ProviderConfig.id)
    provider_config = session.scalar(default_statement)
    if provider_config is None:
        provider_config = session.scalar(statement.order_by(ProviderConfig.id))
    if provider_config is None:
        raise ProviderResolutionError(
            "provider_not_found",
            f"No enabled provider config exists for kind {kind!r}.",
            {"kind": kind},
        )
    return _to_resolved_provider(provider_config)


def resolve_api_key(api_key_ref: str | None) -> str | None:
    if api_key_ref is None or not api_key_ref.strip():
        return None
    if api_key_ref.startswith("env:"):
        key = api_key_ref.removeprefix("env:")
        value = os.getenv(key)
        if value is None:
            raise ProviderResolutionError("api_key_missing", f"Environment variable {key!r} is not set.", {"api_key_ref": api_key_ref})
        return value
    return api_key_ref


def _to_resolved_provider(provider_config: ProviderConfig) -> ResolvedProviderConfig:
    return ResolvedProviderConfig(
        id=provider_config.id,
        name=provider_config.name,
        kind=provider_config.kind,
        provider=provider_config.provider,
        base_url=provider_config.base_url,
        model=provider_config.model,
        api_key_ref=provider_config.api_key_ref,
        temperature=provider_config.temperature,
        settings=provider_config.settings_json or {},
    )
