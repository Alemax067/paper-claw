from __future__ import annotations

from deepagents import SubAgent


def create_paper_claw_subagents() -> list[SubAgent]:
    return [
        {
            "name": "paper-search-specialist",
            "description": "Find papers, compare candidates, and handle search confirmation.",
            "system_prompt": "Focus on paper search, candidate quality, identifier matching, and confirmation readiness.",
        },
        {
            "name": "paper-acquisition-specialist",
            "description": "Plan and verify source/PDF artifact acquisition.",
            "system_prompt": "Focus on artifact availability, upload requirements, and acquisition next steps.",
        },
        {
            "name": "paper-parsing-specialist",
            "description": "Parse papers using TeX source first, then local OCR, then LlamaParse fallback.",
            "system_prompt": "Focus on parse strategy selection, parser failures, and processed document readiness.",
        },
        {
            "name": "paper-analysis-specialist",
            "description": "Generate evidence-grounded paper reports.",
            "system_prompt": "Focus on retrieval evidence, citations, report structure, and unsupported-claim avoidance.",
        },
        {
            "name": "paper-qa-specialist",
            "description": "Answer paper questions using retrieval evidence.",
            "system_prompt": "Focus on concise answers grounded in retrieved chunks with chunk citations.",
        },
    ]
