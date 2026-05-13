from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.db.models import ParsedDocument, ProcessedDocument
from backend.db.repositories import ParsingRepository
from backend.db.types import ParseQualityStatus, ProcessedDocumentStatus, SectionRole

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_PAGE_RE = re.compile(r"<!--\s*page\s+(\d+)\s*-->", re.IGNORECASE)
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
_ARXIV_RE = re.compile(r"\b(?:arXiv:)?(\d{4}\.\d{4,5})(?:v\d+)?\b", re.IGNORECASE)
_URL_RE = re.compile(r"https?://[^\s)\]]+")
_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class SectionPayload:
    heading_path: list[str]
    role: str
    raw_text: str
    cleaned_text: str
    page_start: int | None = None
    page_end: int | None = None


class DocumentProcessingService:
    def __init__(self, session: Session, *, chunk_size_chars: int = 1800, chunk_overlap_chars: int = 200) -> None:
        self.session = session
        self.chunk_size_chars = chunk_size_chars
        self.chunk_overlap_chars = chunk_overlap_chars

    def process_latest_parsed_document(self, paper_id: int, *, regenerate: bool = True) -> ProcessedDocument:
        parsed = self.session.scalar(
            select(ParsedDocument)
            .where(ParsedDocument.paper_id == paper_id)
            .order_by(ParsedDocument.created_at.desc(), ParsedDocument.id.desc())
        )
        if parsed is None:
            raise ValueError(f"Paper {paper_id} has no parsed document.")
        return self.process_parsed_document(parsed.id, regenerate=regenerate)

    def process_parsed_document(self, parsed_document_id: int, *, regenerate: bool = True) -> ProcessedDocument:
        parsed = self.session.get(ParsedDocument, parsed_document_id)
        if parsed is None:
            raise ValueError(f"Parsed document {parsed_document_id} does not exist.")
        if regenerate:
            self.session.execute(delete(ProcessedDocument).where(ProcessedDocument.parsed_document_id == parsed.id))
            self.session.flush()
        else:
            existing = self.session.scalar(select(ProcessedDocument).where(ProcessedDocument.parsed_document_id == parsed.id))
            if existing is not None:
                return existing
        markdown = parsed.markdown_content or parsed.plain_text or ""
        text = _clean_text(parsed.plain_text or markdown)
        version = _next_version(self.session, parsed.paper_id)
        repo = ParsingRepository(self.session)
        processed = repo.create_processed_document(
            parsed.paper_id,
            parsed.id,
            parsed.parse_job_id,
            version=version,
            status=ProcessedDocumentStatus.processing.value,
            content_markdown=markdown,
            content_text=text,
            quality_status=ParseQualityStatus.usable.value,
            quality_summary="Deterministically processed parsed document into sections, chunks, and references.",
            processing_profile="heading_chunk_v1",
            metadata_json={"source_parser": parsed.parser_kind},
        )
        sections = split_markdown_sections(markdown)
        section_ids: list[int] = []
        next_chunk_index = 1
        for index, section in enumerate(sections, start=1):
            row = repo.add_section(
                processed.id,
                index,
                role=section.role,
                heading_path_json=section.heading_path,
                page_start=section.page_start,
                page_end=section.page_end,
                raw_text=section.raw_text,
                cleaned_text=section.cleaned_text,
                token_estimate=_estimate_tokens(section.cleaned_text),
            )
            section_ids.append(row.id)
            for chunk_index, chunk_text in enumerate(_chunk_text(section.cleaned_text, self.chunk_size_chars, self.chunk_overlap_chars), start=1):
                repo.add_chunk(
                    processed.id,
                    f"s{index}-c{chunk_index}",
                    next_chunk_index,
                    chunk_text,
                    role=section.role,
                    heading_path_json=section.heading_path,
                    source_section_ids_json=[row.id],
                    page_start=section.page_start,
                    page_end=section.page_end,
                    token_estimate=_estimate_tokens(chunk_text),
                )
                next_chunk_index += 1
        for reference_index, reference in enumerate(extract_references(sections), start=1):
            repo.add_reference(processed.id, reference_index, reference["raw_text"], **{key: value for key, value in reference.items() if key != "raw_text"})
        processed.status = ProcessedDocumentStatus.ready.value
        processed.metadata_json = {**processed.metadata_json, "section_count": len(sections), "section_ids": section_ids}
        self.session.flush()
        return processed


def split_markdown_sections(markdown: str) -> list[SectionPayload]:
    lines = markdown.splitlines()
    sections: list[SectionPayload] = []
    current_heading: list[str] = ["Document"]
    current_lines: list[str] = []
    current_page: int | None = None
    section_start_page: int | None = None

    def flush() -> None:
        nonlocal current_lines, section_start_page
        raw = "\n".join(current_lines).strip()
        if raw:
            cleaned = _clean_text(raw)
            sections.append(
                SectionPayload(
                    heading_path=current_heading.copy(),
                    role=_classify_role(current_heading[-1], cleaned),
                    raw_text=raw,
                    cleaned_text=cleaned,
                    page_start=section_start_page,
                    page_end=current_page,
                )
            )
        current_lines = []
        section_start_page = current_page

    for line in lines:
        page_match = _PAGE_RE.search(line)
        if page_match:
            current_page = int(page_match.group(1))
            if section_start_page is None:
                section_start_page = current_page
            continue
        heading_match = _HEADING_RE.match(line)
        if heading_match:
            flush()
            level = len(heading_match.group(1))
            heading = heading_match.group(2).strip()
            current_heading = current_heading[: level - 1] + [heading]
            if level == 1:
                sections.append(
                    SectionPayload(
                        heading_path=current_heading.copy(),
                        role=SectionRole.title.value,
                        raw_text=heading,
                        cleaned_text=heading,
                        page_start=current_page,
                        page_end=current_page,
                    )
                )
            continue
        current_lines.append(line)
    flush()
    if not sections and markdown.strip():
        cleaned = _clean_text(markdown)
        sections.append(SectionPayload(["Document"], _classify_role("Document", cleaned), markdown.strip(), cleaned))
    return sections


def extract_references(sections: list[SectionPayload]) -> list[dict[str, object]]:
    references: list[dict[str, object]] = []
    for section in sections:
        if section.role != SectionRole.reference.value:
            continue
        entries = _split_reference_entries(section.cleaned_text)
        for entry in entries:
            doi = _first_match(_DOI_RE, entry)
            arxiv_id = _first_match(_ARXIV_RE, entry)
            url = _first_match(_URL_RE, entry)
            references.append(
                {
                    "raw_text": entry,
                    "normalized_text": _clean_text(entry),
                    "doi": doi.lower() if doi else None,
                    "arxiv_id": arxiv_id,
                    "url": url,
                    "confidence": 0.8 if any([doi, arxiv_id, url]) else 0.5,
                }
            )
    return references


def _split_reference_entries(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 1:
        return [_strip_reference_label(line) for line in lines]
    return [_strip_reference_label(part.strip()) for part in re.split(r"\s+(?=\[?\d+\]?\s+)", text) if part.strip()]


def _strip_reference_label(text: str) -> str:
    return re.sub(r"^(?:\[\d+\]|\d+\.)\s*", "", text).strip()


def _chunk_text(text: str, size: int, overlap: int) -> list[str]:
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        chunks.append(text[start:end].strip())
        if end == len(text):
            break
        start = max(end - overlap, start + 1)
    return [chunk for chunk in chunks if chunk]


def _classify_role(heading: str, text: str) -> str:
    normalized = heading.strip().lower()
    if normalized in {"title", "document"} and len(text) < 500:
        return SectionRole.title.value
    if "abstract" in normalized:
        return SectionRole.abstract.value
    if "appendix" in normalized:
        return SectionRole.appendix.value
    if normalized in {"references", "bibliography", "reference"}:
        return SectionRole.reference.value
    if "caption" in normalized:
        return SectionRole.caption.value
    if "table" in normalized:
        return SectionRole.table.value
    return SectionRole.body.value


def _clean_text(text: str) -> str:
    return _SPACE_RE.sub(" ", text.replace("\r\n", "\n").replace("\r", "\n")).strip()


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4) if text else 0


def _next_version(session: Session, paper_id: int) -> int:
    current = session.scalar(select(func.max(ProcessedDocument.version)).where(ProcessedDocument.paper_id == paper_id))
    return int(current or 0) + 1


def _first_match(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(1 if pattern is _ARXIV_RE else 0).rstrip(".,;") if match else None
