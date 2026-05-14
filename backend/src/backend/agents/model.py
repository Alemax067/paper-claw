from __future__ import annotations

from collections.abc import Callable

from langchain.agents.middleware import ModelRequest, ModelResponse, wrap_model_call
from langchain.chat_models import init_chat_model

from backend.schemas import PaperClawContext


def runtime_model(request: ModelRequest):
    context = request.runtime.context
    if not isinstance(context, PaperClawContext) or not context.model or not context.model.strip():
        return None
    return init_chat_model(
        context.model,
        api_key=context.api_key,
        base_url=context.base_url,
        temperature=context.temperature,
        max_tokens=context.max_tokens,
        timeout=context.timeout,
        max_retries=context.max_retries,
        rate_limiter=context.rate_limiter,
    )


def apply_runtime_model(request: ModelRequest) -> None:
    model = runtime_model(request)
    if model is not None:
        request.model = model


@wrap_model_call
def paper_claw_model_middleware(request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]) -> ModelResponse:
    model = runtime_model(request)
    if model is None:
        return handler(request)
    return handler(request.override(model=model))
