from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import DocumentChunk, Paper, ProcessedDocument, Report
from backend.db.repositories import ReportRepository
from backend.db.types import EvidenceType, ReportSourceScope, ReportStatus, ReportType
from backend.integrations.llm import ChatModelAdapter, FixtureChatModelAdapter, OpenAICompatibleChatModelAdapter
from backend.schemas import ReportGenerationResult, ResolvedProviderConfig, RetrievedChunk
from backend.services.providers import chat_provider_from_settings
from backend.services.retrieval import RetrievalService


class ReportGenerationService:
    def __init__(
        self,
        session: Session,
        *,
        retrieval_service: RetrievalService | None = None,
        adapters: dict[str, ChatModelAdapter] | None = None,
        chat_provider: ResolvedProviderConfig | None = None,
    ) -> None:
        self.session = session
        self.retrieval_service = retrieval_service or RetrievalService(session)
        self.chat_provider = chat_provider
        self.adapters = adapters or {
            "fixture": FixtureChatModelAdapter(),
            "openai_compatible": OpenAICompatibleChatModelAdapter(),
            "openai": OpenAICompatibleChatModelAdapter(),
        }

    def generate_report(
        self,
        paper_id: int,
        *,
        instructions: str | None = None,
        report_type: str = ReportType.paper_summary.value,
        source_scope: str = ReportSourceScope.retrieval.value,
        query: str | None = None,
        selected_chunk_ids: list[int] | None = None,
        provider_name: str | None = None,
        thread_id: int | None = None,
        run_id: int | None = None,
        limit: int = 5,
    ) -> ReportGenerationResult:
        paper = self.session.get(Paper, paper_id)
        if paper is None:
            raise ValueError(f"Paper {paper_id} does not exist.")
        processed = self._latest_processed_document(paper_id)
        if processed is None:
            return self._failed_report(paper, "No processed document exists for this paper.", report_type, source_scope, thread_id, run_id)
        report = ReportRepository(self.session).create(
            f"{paper.title} report",
            thread_id=thread_id,
            run_id=run_id,
            paper_id=paper.id,
            processed_document_id=processed.id,
            report_type=report_type,
            status=ReportStatus.running.value,
            instructions=instructions,
            source_scope=source_scope,
        )
        try:
            provider = self.chat_provider or chat_provider_from_settings()
            evidence = self._select_evidence(paper.id, processed, source_scope, query or instructions or paper.title, selected_chunk_ids, limit)
            markdown = self._adapter_for(provider).generate_text(provider, _messages(paper.title, instructions, evidence, processed))
            evidence_ids = self._persist_evidence(report.id, evidence, paper.id)
            report.status = ReportStatus.succeeded.value
            report.markdown_content = markdown
            report.json_content = {"provider": provider.name, "evidence_chunk_ids": [item.chunk_id for item in evidence]}
            report.source_refs_json = [{"type": "chunk", "id": item.chunk_id} for item in evidence]
            self.session.flush()
            return ReportGenerationResult(report_id=report.id, status=report.status, markdown_content=markdown, json_content=report.json_content, evidence_ids=evidence_ids)
        except Exception as exc:
            report.status = ReportStatus.failed.value
            report.error_message = str(exc)
            self.session.flush()
            return ReportGenerationResult(report_id=report.id, status=report.status, json_content={"error": str(exc)})

    def _select_evidence(
        self,
        paper_id: int,
        processed: ProcessedDocument,
        source_scope: str,
        query: str,
        selected_chunk_ids: list[int] | None,
        limit: int,
    ) -> list[RetrievedChunk]:
        if source_scope == ReportSourceScope.selected_chunks.value:
            if not selected_chunk_ids:
                return []
            chunks = list(self.session.scalars(select(DocumentChunk).where(DocumentChunk.id.in_(selected_chunk_ids)).order_by(DocumentChunk.chunk_index)))
            return [_chunk_to_retrieved(chunk, 1.0, "lexical") for chunk in chunks]
        if source_scope == ReportSourceScope.full_document.value:
            chunks = list(
                self.session.scalars(
                    select(DocumentChunk)
                    .where(DocumentChunk.processed_document_id == processed.id)
                    .order_by(DocumentChunk.chunk_index)
                    .limit(limit)
                )
            )
            return [_chunk_to_retrieved(chunk, 1.0, "lexical") for chunk in chunks]
        return self.retrieval_service.retrieve(paper_id, query, limit=limit)

    def _persist_evidence(self, report_id: int, evidence: list[RetrievedChunk], paper_id: int) -> list[int]:
        ids: list[int] = []
        repo = ReportRepository(self.session)
        for item in evidence:
            row = repo.add_evidence(
                report_id,
                EvidenceType.chunk.value,
                chunk_id=item.chunk_id,
                paper_id=paper_id,
                quote_text=item.content_text[:1000],
                note=f"{item.retrieval_mode} score={item.score:.4f}",
            )
            ids.append(row.id)
        return ids

    def _latest_processed_document(self, paper_id: int) -> ProcessedDocument | None:
        return self.session.scalar(
            select(ProcessedDocument)
            .where(ProcessedDocument.paper_id == paper_id)
            .order_by(ProcessedDocument.version.desc(), ProcessedDocument.id.desc())
        )

    def _adapter_for(self, provider: ResolvedProviderConfig) -> ChatModelAdapter:
        adapter = self.adapters.get(provider.provider)
        if adapter is None:
            raise ValueError(f"No chat adapter configured for provider {provider.provider!r}.")
        return adapter

    def _failed_report(
        self,
        paper: Paper,
        error: str,
        report_type: str,
        source_scope: str,
        thread_id: int | None,
        run_id: int | None,
    ) -> ReportGenerationResult:
        report = ReportRepository(self.session).create(
            f"{paper.title} report",
            thread_id=thread_id,
            run_id=run_id,
            paper_id=paper.id,
            report_type=report_type,
            status=ReportStatus.failed.value,
            source_scope=source_scope,
            error_message=error,
        )
        self.session.flush()
        return ReportGenerationResult(report_id=report.id, status=report.status, json_content={"error": error})


def _messages(paper_title: str, instructions: str | None, evidence: list[RetrievedChunk], processed: ProcessedDocument) -> list[dict]:
    evidence_text = "\n\n".join(f"[chunk:{item.chunk_id}] {item.content_text}" for item in evidence)
    return [
        {
            "role": "system",
            "content": "You write evidence-grounded academic paper reports. Cite evidence as [chunk:<id>] and do not invent unsupported claims.",
        },
        {
            "role": "user",
            "content": f"Paper: {paper_title}\nInstructions: {instructions or 'Write a concise structured report.'}\nProcessed document id: {processed.id}\nEvidence:\n{evidence_text}",
        },
    ]


def _chunk_to_retrieved(chunk: DocumentChunk, score: float, mode: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk.id,
        processed_document_id=chunk.processed_document_id,
        content_text=chunk.content_text,
        score=score,
        retrieval_mode=mode,
        metadata={"chunk_key": chunk.chunk_key, "heading_path": chunk.heading_path_json},
    )
