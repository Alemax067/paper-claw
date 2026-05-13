from __future__ import annotations

from backend.db.models import Artifact, Paper, Report, ReportEvidence
from backend.db.repositories import ParsingRepository, ThreadRepository
from backend.db.types import ArtifactKind, EvidenceType, PaperArtifactRole, ReportType
from backend.services.storage import ArtifactStorageService
from backend.integrations.storage import LocalStorage


def test_threads_read_model(client, session):
    thread = ThreadRepository(session).create("API thread")
    ThreadRepository(session).add_message(thread.id, "user", "hello")
    session.commit()

    list_response = client.get("/api/threads")
    detail_response = client.get(f"/api/threads/{thread.id}")

    assert list_response.status_code == 200
    assert list_response.json()[0]["title"] == "API thread"
    assert detail_response.status_code == 200
    assert detail_response.json()["messages"][0]["content_text"] == "hello"


def test_paper_detail_includes_aggregate_state(client, session, tmp_path):
    paper = Paper(title="API paper", authors_json=["A"])
    session.add(paper)
    session.flush()
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"pdf")
    ArtifactStorageService(session, LocalStorage(tmp_path / "files")).register_local_pdf(paper.id, source)
    repo = ParsingRepository(session)
    job = repo.create_parse_job(paper.id, status="succeeded", strategy="fixture")
    parsed = repo.create_parsed_document(paper.id, job.id, "fixture")
    repo.create_processed_document(paper.id, parsed.id, job.id, status="ready")
    report = Report(title="API report", paper_id=paper.id, report_type=ReportType.paper_summary.value, markdown_content="report")
    session.add(report)
    session.commit()

    response = client.get(f"/api/papers/{paper.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "API paper"
    assert payload["artifacts"][0]["kind"] == ArtifactKind.pdf.value
    assert payload["parse_jobs"][0]["status"] == "succeeded"
    assert payload["processed_documents"][0]["status"] == "ready"
    assert payload["reports"][0]["title"] == "API report"


def test_report_detail_includes_evidence(client, session):
    paper = Paper(title="Evidence paper")
    session.add(paper)
    session.flush()
    report = Report(title="Evidence report", paper_id=paper.id, report_type=ReportType.paper_summary.value, markdown_content="report")
    session.add(report)
    session.flush()
    session.add(ReportEvidence(report_id=report.id, evidence_type=EvidenceType.paper.value, paper_id=paper.id, quote_text="quote"))
    session.commit()

    response = client.get(f"/api/reports/{report.id}")

    assert response.status_code == 200
    assert response.json()["evidence"][0]["quote_text"] == "quote"
