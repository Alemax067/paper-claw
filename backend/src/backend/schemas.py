from __future__ import annotations

from dataclasses import dataclass
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
