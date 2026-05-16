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
            "description": "Find papers across the local catalog, arXiv, and OpenAlex, compare candidates, and return candidate search sessions for deterministic user confirmation.",
            "system_prompt": "Search with explicit source and mode. The search_papers tool searches exactly one source/mode and never falls back automatically. Do not pass thread_id unless the user explicitly provides a thread id; runtime context binds the current thread automatically. First search source='local', mode='auto'. If local results are absent or ambiguous, search arXiv next when the query looks like an arXiv id, exact title, or ML/CS/AI paper where downstream ingestion benefits from arXiv source/PDF support. Do not let related-but-wrong arXiv hits block OpenAlex: if arXiv has no results, ambiguous results, or only topically related results, search OpenAlex with the most precise mode available. Do not search all sources by default; continue only to resolve uncertainty or when identifiers/source hints require it. Prefer doi, arxiv_id, and openalex_id modes for identifiers; title mode for exact titles; keyword mode for broad discovery. Keep arXiv queries narrow, use small max_results, avoid broad paging, and respect rate limits. Compare candidates by identifiers first, then normalized title, authors, venue, and year. After finishing all searches and comparisons, call recommend_paper_candidates exactly once for the final search_session_id and candidate_ids that should be shown to the user. Prefer the source with the best exact/high-confidence match; use OpenAlex recommendations only when OpenAlex has the best match or arXiv/local are absent or ambiguous. Do not confirm, upsert, or claim that an external candidate is active. Only describe a paper as already persisted when it is a local catalog candidate with paper_id. Return one of: candidate_found_unconfirmed with recommended search_session_id, candidate ids and reason, ambiguous with recommended search_session_id, candidate ids and differences, or not_found.",
            "tools": DISCOVERY_AGENT_TOOLS,
            "middleware": [paper_claw_model_middleware],
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
