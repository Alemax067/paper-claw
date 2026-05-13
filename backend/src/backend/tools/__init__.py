from backend.tools.paper_acquisition import acquire_paper_artifacts, register_local_paper_pdf, register_local_paper_source
from backend.tools.paper_parsing import parse_paper, process_paper_document
from backend.tools.paper_qa import embed_paper_chunks, retrieve_paper_evidence
from backend.tools.paper_reports import answer_paper_question, generate_paper_report
from backend.tools.paper_search import confirm_paper_candidate, get_paper, search_papers

PAPER_CLAW_TOOLS = [
    search_papers,
    confirm_paper_candidate,
    get_paper,
    acquire_paper_artifacts,
    register_local_paper_pdf,
    register_local_paper_source,
    parse_paper,
    process_paper_document,
    embed_paper_chunks,
    retrieve_paper_evidence,
    generate_paper_report,
    answer_paper_question,
]

__all__ = [
    "PAPER_CLAW_TOOLS",
    "acquire_paper_artifacts",
    "answer_paper_question",
    "confirm_paper_candidate",
    "embed_paper_chunks",
    "generate_paper_report",
    "get_paper",
    "parse_paper",
    "process_paper_document",
    "register_local_paper_pdf",
    "register_local_paper_source",
    "retrieve_paper_evidence",
    "search_papers",
]
