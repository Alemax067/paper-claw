from __future__ import annotations

from typing import Any

from langchain.agents.middleware import ModelRequest, ModelResponse, wrap_model_call
from langchain.chat_models import init_chat_model

from backend.schemas import PaperClawContext


def apply_runtime_model(request: ModelRequest) -> None:
    context = request.runtime.context
    if isinstance(context, PaperClawContext) and context.model:
        request.model = init_chat_model(
            context.model,
            api_key=context.api_key,
            base_url=context.base_url,
            temperature=context.temperature,
            max_tokens=context.max_tokens,
            timeout=context.timeout,
            max_retries=context.max_retries,
            rate_limiter=context.rate_limiter,
        )


@wrap_model_call
def paper_claw_model_middleware(request: ModelRequest, handler: Any) -> ModelResponse:
    apply_runtime_model(request)
    return handler(request)
