from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from deepagents import create_deep_agent

from backend.agents.context import PaperClawContext
from backend.agents.model import paper_claw_model_middleware
from backend.agents.prompts import PAPER_CLAW_SYSTEM_PROMPT
from backend.agents.subagents import create_paper_claw_subagents
from backend.tools import PAPER_CLAW_TOOLS


def create_paper_claw_agent(model: str | BaseChatModel | None = None):
    return create_deep_agent(
        model=model,
        tools=PAPER_CLAW_TOOLS,
        system_prompt=PAPER_CLAW_SYSTEM_PROMPT,
        middleware=[paper_claw_model_middleware],
        subagents=create_paper_claw_subagents(),
        context_schema=PaperClawContext,
        name="paper-claw",
    )
