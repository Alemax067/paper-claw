from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ServiceError(BaseModel):
    code: str
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


class ProviderResolutionError(Exception):
    def __init__(self, code: str, message: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.error = ServiceError(code=code, message=message, detail=detail or {})


class ResolvedProviderConfig(BaseModel):
    id: int
    name: str
    kind: str
    provider: str
    base_url: str | None = None
    model: str | None = None
    api_key_ref: str | None = None
    temperature: float | None = None
    settings: dict[str, Any] = Field(default_factory=dict)


class PaperIdentifierInput(BaseModel):
    identifier_type: str
    identifier_value: str
    is_primary: bool = False


class PaperSearchResult(BaseModel):
    source: str
    source_record_id: str | None = None
    title: str
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    openalex_id: str | None = None
    landing_page_url: str | None = None
    pdf_url: str | None = None
    score: float | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class ParsedDocumentPayload(BaseModel):
    strategy: str
    parser_kind: str
    plain_text: str | None = None
    markdown_content: str | None = None
    json_content: dict[str, Any] = Field(default_factory=dict)
    quality_summary: str | None = None
    warnings: list[str] = Field(default_factory=list)


class RetrievedChunk(BaseModel):
    chunk_id: int
    processed_document_id: int
    content_text: str
    score: float
    retrieval_mode: Literal["vector", "lexical"]
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReportGenerationResult(BaseModel):
    report_id: int
    status: str
    markdown_content: str | None = None
    json_content: dict[str, Any] | None = None
    evidence_ids: list[int] = Field(default_factory=list)


class AgentMessageRequest(BaseModel):
    thread_id: int | None = None
    message: str
    active_paper_id: int | None = None
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = 0.2
    max_tokens: int = 4096
    timeout: int = 60
    max_retries: int = 2
    chat_provider_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentMessageResponse(BaseModel):
    thread_id: int
    run_id: int
    assistant_message_id: int | None = None
    status: str
    message: str | None = None
    error: str | None = None


class MessageRead(BaseModel):
    id: int
    thread_id: int
    role: str
    content_text: str | None = None
    content_json: dict[str, Any] | None = None
    source: str
    run_id: int | None = None
    created_at: datetime


class RunEventRead(BaseModel):
    id: int
    run_id: int
    sequence: int
    event_type: str
    level: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class RunRead(BaseModel):
    id: int
    thread_id: int | None = None
    workflow: str
    status: str
    error_message: str | None = None
    input_json: dict[str, Any] | None = None
    output_json: dict[str, Any] | None = None
    events: list[RunEventRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ThreadSummary(BaseModel):
    id: int
    title: str
    surface: str
    status: str
    current_focus_paper_id: int | None = None
    created_at: datetime
    updated_at: datetime


class ThreadDetail(ThreadSummary):
    messages: list[MessageRead] = Field(default_factory=list)
    runs: list[RunRead] = Field(default_factory=list)


class ArtifactRead(BaseModel):
    id: int
    kind: str
    status: str
    storage_backend: str
    storage_uri: str | None = None
    original_filename: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    checksum_sha256: str | None = None


class PaperSummary(BaseModel):
    id: int
    title: str
    abstract: str | None = None
    year: int | None = None
    venue: str | None = None
    status: str
    current_pdf_url: str | None = None


class PaperDetail(PaperSummary):
    authors: list[Any] = Field(default_factory=list)
    identifiers: list[dict[str, Any]] = Field(default_factory=list)
    source_records: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    parse_jobs: list[dict[str, Any]] = Field(default_factory=list)
    processed_documents: list[dict[str, Any]] = Field(default_factory=list)
    reports: list[dict[str, Any]] = Field(default_factory=list)


class SearchCandidateRead(BaseModel):
    id: int
    rank: int
    source: str
    source_record_id: str | None = None
    paper_id: int | None = None
    title: str
    abstract: str | None = None
    authors: list[Any] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    openalex_id: str | None = None
    landing_page_url: str | None = None
    pdf_url: str | None = None
    score: float | None = None


class SearchSessionRead(BaseModel):
    id: int
    thread_id: int | None = None
    run_id: int | None = None
    query_text: str
    status: str
    selected_candidate_id: int | None = None
    candidates: list[SearchCandidateRead] = Field(default_factory=list)


class ConfirmSearchCandidateRequest(BaseModel):
    candidate_id: int
    update_thread_focus: bool = True


class RejectSearchSessionRequest(BaseModel):
    reason: str | None = None


class ApprovalRequest(BaseModel):
    decision: Literal["approve", "reject", "revise", "cancel"]
    comment: str | None = None


class ReportSummary(BaseModel):
    id: int
    title: str
    paper_id: int | None = None
    processed_document_id: int | None = None
    report_type: str
    status: str
    source_scope: str
    created_at: datetime
    updated_at: datetime


class ReportRead(ReportSummary):
    markdown_content: str | None = None
    json_content: dict[str, Any] | None = None
    source_refs: list[Any] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)


@dataclass(frozen=True)
class PaperClawContext:
    thread_id: int | None = None
    run_id: int | None = None
    active_paper_id: int | None = None
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = 0.2
    max_tokens: int = 4096
    timeout: int = 60
    max_retries: int = 2
    rate_limiter: Any | None = None
    chat_provider_name: str | None = None
    embedding_provider_name: str | None = None
