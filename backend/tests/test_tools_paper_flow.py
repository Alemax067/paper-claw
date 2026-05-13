from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from backend.db.models import Paper, ProviderConfig
from backend.db.repositories import ParsingRepository
from backend.db.types import ProcessedDocumentStatus, ProviderKind
from backend.tools import PAPER_CLAW_TOOLS
from backend.tools.context import set_tool_session_factory
from backend.tools.paper_qa import retrieve_paper_evidence
from backend.tools.paper_reports import generate_paper_report
from backend.tools.paper_search import get_paper


def test_expected_tool_names_exist():
    names = {tool.name for tool in PAPER_CLAW_TOOLS}
    assert {
        "search_papers",
        "confirm_paper_candidate",
        "get_paper",
        "acquire_paper_artifacts",
        "parse_paper",
        "process_paper_document",
        "embed_paper_chunks",
        "retrieve_paper_evidence",
        "generate_paper_report",
        "answer_paper_question",
    }.issubset(names)


def test_tools_can_be_invoked_directly(session, engine):
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    provider = ProviderConfig(name="fixture-chat", kind=ProviderKind.chat.value, provider="fixture", enabled=True, is_default=True, model="fixture")
    paper = Paper(title="Tool Paper")
    session.add_all([provider, paper])
    session.flush()
    repo = ParsingRepository(session)
    job = repo.create_parse_job(paper.id, status="succeeded", strategy="fixture")
    parsed = repo.create_parsed_document(paper.id, job.id, "fixture", plain_text="retrieval evidence", markdown_content="retrieval evidence")
    processed = repo.create_processed_document(paper.id, parsed.id, job.id, status=ProcessedDocumentStatus.ready.value, content_text="retrieval evidence", content_markdown="retrieval evidence")
    repo.add_chunk(processed.id, "c1", 1, "retrieval evidence")
    session.commit()
    set_tool_session_factory(factory)
    try:
        paper_result = get_paper.invoke({"paper_id": paper.id})
        retrieval_result = retrieve_paper_evidence.invoke({"paper_id": paper.id, "query": "retrieval"})
        report_result = generate_paper_report.invoke({"paper_id": paper.id, "instructions": "retrieval"})
    finally:
        set_tool_session_factory(None)

    assert paper_result["title"] == "Tool Paper"
    assert retrieval_result["chunks"][0]["content"] == "retrieval evidence"
    assert report_result["status"] == "succeeded"
