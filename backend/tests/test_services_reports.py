from __future__ import annotations

from types import SimpleNamespace

from backend.db.models import Paper, ProviderConfig, Report, ReportEvidence
from backend.db.repositories import ParsingRepository
from backend.db.types import ProcessedDocumentStatus, ProviderKind, ReportSourceScope, ReportStatus, SectionRole
from backend.integrations.llm.openai_compatible import OpenAICompatibleChatModelAdapter
from backend.schemas import ResolvedProviderConfig
from backend.services.reports import ReportGenerationService


def add_chat_provider(session, *, provider="fixture"):
    config = ProviderConfig(
        name="fixture-chat",
        kind=ProviderKind.chat.value,
        provider=provider,
        enabled=True,
        is_default=True,
        model="fixture-chat-model",
        settings_json={"title": "Generated Fixture Report"},
    )
    session.add(config)
    session.commit()
    return config


def create_processed_paper(session):
    paper = Paper(title="Report Paper")
    session.add(paper)
    session.flush()
    repo = ParsingRepository(session)
    job = repo.create_parse_job(paper.id, status="succeeded", strategy="fixture")
    parsed = repo.create_parsed_document(paper.id, job.id, "fixture", plain_text="text", markdown_content="text")
    processed = repo.create_processed_document(
        paper.id,
        parsed.id,
        job.id,
        status=ProcessedDocumentStatus.ready.value,
        content_text="text",
        content_markdown="text",
    )
    alpha = repo.add_chunk(processed.id, "alpha", 1, "retrieval evidence alpha", role=SectionRole.body.value)
    beta = repo.add_chunk(processed.id, "beta", 2, "citation reference beta", role=SectionRole.reference.value)
    session.commit()
    return paper, processed, [alpha, beta]


def test_generate_report_fails_cleanly_without_processed_document(session):
    add_chat_provider(session)
    paper = Paper(title="Unprocessed")
    session.add(paper)
    session.commit()

    result = ReportGenerationService(session).generate_report(paper.id)

    assert result.status == ReportStatus.failed.value
    report = session.get(Report, result.report_id)
    assert "No processed document" in report.error_message


def test_fixture_llm_generates_report_and_persists_evidence(session):
    add_chat_provider(session)
    paper, _, chunks = create_processed_paper(session)

    result = ReportGenerationService(session).generate_report(
        paper.id,
        instructions="Discuss retrieval evidence.",
        source_scope=ReportSourceScope.selected_chunks.value,
        selected_chunk_ids=[chunks[0].id],
    )

    assert result.status == ReportStatus.succeeded.value
    assert "Generated Fixture Report" in result.markdown_content
    evidence = session.query(ReportEvidence).one()
    assert evidence.chunk_id == chunks[0].id
    assert evidence.paper_id == paper.id
    assert "retrieval evidence" in evidence.quote_text


def test_retrieval_selects_evidence_chunks(session):
    add_chat_provider(session)
    paper, _, _ = create_processed_paper(session)

    result = ReportGenerationService(session).generate_report(paper.id, instructions="citation reference", limit=1)

    report = session.get(Report, result.report_id)
    assert result.status == ReportStatus.succeeded.value
    assert len(report.evidence) == 1
    assert "citation reference" in report.evidence[0].quote_text


def test_full_document_scope_uses_ordered_chunks(session):
    add_chat_provider(session)
    paper, _, chunks = create_processed_paper(session)

    result = ReportGenerationService(session).generate_report(paper.id, source_scope=ReportSourceScope.full_document.value, limit=2)

    report = session.get(Report, result.report_id)
    assert [evidence.chunk_id for evidence in report.evidence] == [chunks[0].id, chunks[1].id]


def test_openai_compatible_chat_adapter_uses_injected_client():
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="model output"))])
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return response

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    provider = ResolvedProviderConfig(id=1, name="chat", kind="chat", provider="openai_compatible", model="model", temperature=0.2, settings={"max_tokens": 100, "timeout": 30})

    text = OpenAICompatibleChatModelAdapter(client).generate_text(provider, [{"role": "user", "content": "hi"}])

    assert text == "model output"
    assert calls[0]["model"] == "model"
    assert calls[0]["max_tokens"] == 100
