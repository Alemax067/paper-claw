from __future__ import annotations

from deepagents import SubAgent

from backend.agents.model import paper_claw_model_middleware
from backend.tools import DISCOVERY_AGENT_TOOLS, EVIDENCE_AGENT_TOOLS, INGESTION_AGENT_TOOLS, REPORT_AGENT_TOOLS

_CONFIRM_INTERRUPT = {"allowed_decisions": ["approve", "edit", "reject"]}
_REGISTER_INTERRUPT = {"allowed_decisions": ["approve", "edit", "reject"]}


def create_paper_claw_subagents() -> list[SubAgent]:
    return [
        {
            "name": "paper-discovery-specialist",
            "description": "Find papers, compare candidates, and confirm the user's chosen paper.",
            "system_prompt": "Search local and external sources for papers. Compare candidates by title, identifiers, authors, venue, and year. When a candidate should become the active paper, call the confirmation tool and rely on human approval before it executes. Return candidate ids, ambiguity, and the confirmed paper id when available.",
            "tools": DISCOVERY_AGENT_TOOLS,
            "middleware": [paper_claw_model_middleware],
            "interrupt_on": {"confirm_paper_candidate": _CONFIRM_INTERRUPT},
        },
        {
            "name": "paper-ingestion-specialist",
            "description": "Advance the active paper through artifact acquisition, parsing, processing, and retrieval readiness.",
            "system_prompt": "Use the active paper by default. Inspect pipeline status, acquire available artifacts, parse the best available artifact, and process the parsed document. Continue until the paper is ready for retrieval or a real blocker requires user input. Report ready, waiting_for_user, or failed with the blocking reason.",
            "tools": INGESTION_AGENT_TOOLS,
            "middleware": [paper_claw_model_middleware],
            "interrupt_on": {"register_local_paper_pdf": _REGISTER_INTERRUPT, "register_local_paper_source": _REGISTER_INTERRUPT},
        },
        {
            "name": "paper-evidence-specialist",
            "description": "Retrieve and compress evidence chunks for paper questions.",
            "system_prompt": "Use the active paper by default. Retrieve evidence for the requested question or topic. Return concise evidence packs with chunk ids, short quotes, relevance notes, and gaps. Do not write the final user-facing answer.",
            "tools": EVIDENCE_AGENT_TOOLS,
            "middleware": [paper_claw_model_middleware],
        },
        {
            "name": "paper-report-specialist",
            "description": "Generate persisted evidence-grounded paper reports when explicitly requested.",
            "system_prompt": "Use the active paper by default. Generate persisted reports only when the user asks for a report, summary document, review, or structured long-form analysis. Return report id, status, and a brief summary.",
            "tools": REPORT_AGENT_TOOLS,
            "middleware": [paper_claw_model_middleware],
        },
    ]
