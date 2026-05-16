from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from backend.db.models import AgentRun, AgentRunEvent, Paper, Thread
from backend.db.repositories import ParsingRepository
from backend.db.types import ProcessedDocumentStatus, RunStatus, WorkflowName
from backend.schemas import PaperClawContext, ResolvedProviderConfig
from backend.tools import DISCOVERY_AGENT_TOOLS, EVIDENCE_AGENT_TOOLS, INGESTION_AGENT_TOOLS, MAIN_AGENT_TOOLS, PAPER_CLAW_TOOLS, REPORT_AGENT_TOOLS
from backend.tools.context import set_tool_session_factory, tool_runtime_context
from backend.tools.paper_qa import retrieve_paper_evidence
from backend.tools.paper_reports import generate_paper_report
from backend.tools.paper_search import get_paper, recommend_paper_candidates, search_papers


def test_expected_tool_names_exist():
    assert {tool.name for tool in PAPER_CLAW_TOOLS} == {tool.name for tool in MAIN_AGENT_TOOLS}
    assert {tool.name for tool in MAIN_AGENT_TOOLS} == {
        "get_active_paper",
        "set_thread_focus",
        "get_paper",
        "search_local_papers",
        "get_paper_pipeline_status",
        "list_paper_artifacts",
        "list_paper_reports",
    }
    assert {tool.name for tool in DISCOVERY_AGENT_TOOLS} == {"search_papers", "recommend_paper_candidates", "get_paper"}
    assert {tool.name for tool in INGESTION_AGENT_TOOLS} == {
        "get_paper_pipeline_status",
        "list_paper_artifacts",
        "acquire_paper_artifacts",
        "register_local_paper_pdf",
        "register_local_paper_source",
        "parse_paper",
        "process_paper_document",
    }
    assert {tool.name for tool in EVIDENCE_AGENT_TOOLS} == {"get_paper_pipeline_status", "retrieve_paper_evidence"}
    assert {tool.name for tool in REPORT_AGENT_TOOLS} == {"get_paper_pipeline_status", "list_paper_reports", "generate_paper_report"}


def test_search_papers_returns_rich_local_candidate_payload(session, engine):
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    paper = Paper(title="Recursive Multi-Agent Systems", venue="arXiv", year=2024, authors_json=["A"])
    session.add(paper)
    session.commit()
    set_tool_session_factory(factory)
    try:
        result = search_papers.invoke({"query": "Recursive Multi-Agent Systems", "source": "local", "mode": "title"})
    finally:
        set_tool_session_factory(None)

    assert result["source"] == "local"
    assert result["candidates"][0]["title"] == "Recursive Multi-Agent Systems"
    assert result["candidates"][0]["venue"] == "arXiv"


def test_search_papers_records_candidate_found_event(session, engine):
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    thread = Thread(title="Search thread")
    paper = Paper(title="Recursive Multi-Agent Systems", venue="arXiv", year=2024, authors_json=["A"])
    session.add_all([thread, paper])
    session.flush()
    run = AgentRun(workflow=WorkflowName.paper_qa.value, thread_id=thread.id, status=RunStatus.running.value)
    session.add(run)
    session.commit()
    set_tool_session_factory(factory)
    try:
        with tool_runtime_context(PaperClawContext(thread_id=thread.id, run_id=run.id)):
            result = search_papers.invoke({"query": "Recursive Multi-Agent Systems", "source": "local", "mode": "title"})
    finally:
        set_tool_session_factory(None)

    event = session.query(AgentRunEvent).filter_by(run_id=run.id, event_type="search_candidates_found").one()
    assert event.payload_json["search_session_id"] == result["search_session_id"]
    assert event.payload_json["candidate_count"] == 1
    assert event.payload_json["candidate_ids"] == [result["candidates"][0]["id"]]



def test_recommend_paper_candidates_records_final_recommendation_event(session, engine):
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    thread = Thread(title="Search thread")
    paper = Paper(title="Recursive Multi-Agent Systems", venue="arXiv", year=2024, authors_json=["A"])
    session.add_all([thread, paper])
    session.flush()
    run = AgentRun(workflow=WorkflowName.paper_qa.value, thread_id=thread.id, status=RunStatus.running.value)
    session.add(run)
    session.commit()
    set_tool_session_factory(factory)
    try:
        with tool_runtime_context(PaperClawContext(thread_id=thread.id, run_id=run.id)):
            search_result = search_papers.invoke({"query": "Recursive Multi-Agent Systems", "source": "local", "mode": "title"})
            result = recommend_paper_candidates.invoke(
                {
                    "search_session_id": search_result["search_session_id"],
                    "candidate_ids": [search_result["candidates"][0]["id"]],
                    "reason": "Exact local title match",
                }
            )
    finally:
        set_tool_session_factory(None)

    assert result["status"] == "candidate_found_unconfirmed"
    event = session.query(AgentRunEvent).filter_by(run_id=run.id, event_type="paper_candidates_recommended").one()
    assert event.payload_json["search_session_id"] == search_result["search_session_id"]
    assert event.payload_json["candidate_ids"] == [search_result["candidates"][0]["id"]]
    assert event.payload_json["reason"] == "Exact local title match"



def test_search_papers_runtime_thread_overrides_model_thread_argument(session, engine):
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    thread = Thread(title="Search thread")
    paper = Paper(title="Recursive Multi-Agent Systems", venue="arXiv", year=2024, authors_json=["A"])
    session.add_all([thread, paper])
    session.flush()
    run = AgentRun(workflow=WorkflowName.paper_qa.value, thread_id=thread.id, status=RunStatus.running.value)
    session.add(run)
    session.commit()
    set_tool_session_factory(factory)
    try:
        with tool_runtime_context(PaperClawContext(thread_id=thread.id, run_id=run.id)):
            result = search_papers.invoke({"query": "Recursive Multi-Agent Systems", "source": "local", "mode": "title", "thread_id": 999999})
    finally:
        set_tool_session_factory(None)

    assert result["candidates"][0]["title"] == "Recursive Multi-Agent Systems"
    event = session.query(AgentRunEvent).filter_by(run_id=run.id, event_type="search_candidates_found").one()
    assert event.payload_json["search_session_id"] == result["search_session_id"]



def test_search_papers_records_candidate_not_found_event(session, engine):
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    thread = Thread(title="Search thread")
    session.add(thread)
    session.flush()
    run = AgentRun(workflow=WorkflowName.paper_qa.value, thread_id=thread.id, status=RunStatus.running.value)
    session.add(run)
    session.commit()
    set_tool_session_factory(factory)
    try:
        with tool_runtime_context(PaperClawContext(thread_id=thread.id, run_id=run.id)):
            result = search_papers.invoke({"query": "Missing Paper", "source": "local", "mode": "title"})
    finally:
        set_tool_session_factory(None)

    event = session.query(AgentRunEvent).filter_by(run_id=run.id, event_type="search_candidates_not_found").one()
    assert event.payload_json["search_session_id"] == result["search_session_id"]
    assert event.payload_json["candidate_count"] == 0
    assert event.payload_json["candidate_ids"] == []



def test_tools_can_be_invoked_directly(session, engine, monkeypatch):
    monkeypatch.setattr(
        "backend.services.embeddings.embedding_provider_from_settings",
        lambda: ResolvedProviderConfig(id=0, name="fixture-embedding", kind="embedding", provider="fixture", model="fixture-embedding-v1"),
    )
    monkeypatch.setattr(
        "backend.services.reports.chat_provider_from_settings",
        lambda: ResolvedProviderConfig(id=0, name="fixture-chat", kind="chat", provider="fixture", model="fixture", settings={"title": "Tool Report"}),
    )
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    paper = Paper(title="Tool Paper")
    session.add(paper)
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
