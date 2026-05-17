from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.db.models import ParsedDocument, ProcessedDocument
from backend.db.repositories import ParsingRepository
from backend.db.types import PaperStatus, ParseQualityStatus, ProcessedDocumentStatus, SectionRole
from backend.integrations.parsers.cleaning import clean_markdown_text
from backend.services.embeddings import EmbeddingService

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_PAGE_RE = re.compile(r"<!--\s*page\s+(\d+)\s*-->", re.IGNORECASE)
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
_ARXIV_RE = re.compile(r"\b(?:arXiv:)?(\d{4}\.\d{4,5})(?:v\d+)?\b", re.IGNORECASE)
_URL_RE = re.compile(r"https?://[^\s)\]]+")
_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
_SPACE_RE = re.compile(r"\s+")
_REFERENCE_START_RE = re.compile(r"^(?P<label>(?:\[\d+\]|\d+\.|\d+\)|-))\s+(?P<body>.+)")
_TITLE_QUOTE_RE = re.compile(r"[\"“](?P<title>[^\"”]{8,})[\"”]")


@dataclass(frozen=True)
class SectionPayload:
    heading_path: list[str]
    role: str
    raw_text: str
    cleaned_text: str
    page_start: int | None = None
    page_end: int | None = None


@dataclass(frozen=True)
class NormalizedDocumentPayload:
    markdown: str
    text: str
    metadata: dict[str, object]


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
        normalized = normalize_parsed_document(parsed)
        sections = split_markdown_sections(normalized.markdown)
        analysis_text = _clean_text("\n\n".join(section.cleaned_text for section in sections if section.role != SectionRole.reference.value))
        version = _next_version(self.session, parsed.paper_id)
        repo = ParsingRepository(self.session)
        processed = repo.create_processed_document(
            parsed.paper_id,
            parsed.id,
            parsed.parse_job_id,
            version=version,
            status=ProcessedDocumentStatus.processing.value,
            content_markdown=normalized.markdown,
            content_text=analysis_text,
            quality_status=ParseQualityStatus.usable.value,
            quality_summary="Normalized parsed document into frontend markdown, sections, chunks, and structured references.",
            processing_profile="normalized_heading_chunk_v2",
            metadata_json=normalized.metadata,
        )
        section_ids: list[int] = []
        next_chunk_index = 1
        skipped_chunk_roles: set[str] = set()
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
            if section.role == SectionRole.reference.value:
                skipped_chunk_roles.add(section.role)
                continue
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
        self.session.flush()
        metadata = {
            **processed.metadata_json,
            "section_count": len(sections),
            "section_ids": section_ids,
            "skipped_chunk_roles": sorted(skipped_chunk_roles),
        }
        try:
            metadata["embedded_chunk_count"] = EmbeddingService(self.session).embed_missing_chunks(parsed.paper_id)
        except Exception as exc:
            metadata["embedding_error"] = str(exc)
        processed.status = ProcessedDocumentStatus.ready.value
        processed.metadata_json = metadata
        processed.paper.status = PaperStatus.processed.value
        self.session.flush()
        return processed


def normalize_parsed_document(parsed: ParsedDocument) -> NormalizedDocumentPayload:
    markdown = clean_markdown_text(parsed.markdown_content or parsed.plain_text or "")
    return NormalizedDocumentPayload(
        markdown=markdown,
        text=_clean_text(markdown),
        metadata={
            "source_parser": parsed.parser_kind,
            "normalization_profile": "markdown_structure_v1",
            "analysis_excludes_roles": [SectionRole.reference.value],
        },
    )


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
        for raw_label, entry in _split_reference_entries(section.raw_text):
            normalized = _clean_text(entry)
            if not normalized:
                continue
            doi = _first_match(_DOI_RE, normalized)
            arxiv_id = _first_match(_ARXIV_RE, normalized)
            url = _first_match(_URL_RE, normalized)
            year = _extract_year(normalized)
            authors = _extract_reference_authors(normalized)
            title = _extract_reference_title(normalized, authors)
            source, other = _extract_reference_source(normalized, title, authors, year, doi, arxiv_id, url)
            references.append(
                {
                    "raw_text": entry,
                    "label": raw_label,
                    "normalized_text": normalized,
                    "title": title,
                    "authors_json": authors,
                    "year": year,
                    "doi": doi.lower() if doi else None,
                    "arxiv_id": arxiv_id,
                    "url": url,
                    "confidence": _reference_confidence(title, authors, doi, arxiv_id, url),
                    "metadata_json": {"parser": "deterministic_reference_v1", "source": source, "other": other},
                }
            )
    return references


def _split_reference_entries(text: str) -> list[tuple[str | None, str]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    entries: list[tuple[str | None, list[str]]] = []
    for line in lines:
        line = re.sub(r"^[-*]\s+", "- ", line)
        match = _REFERENCE_START_RE.match(line)
        if match:
            entries.append((match.group("label").strip("[]().-"), [match.group("body").strip()]))
        elif entries:
            entries[-1][1].append(line)
        else:
            entries.append((None, [line]))
    if len(entries) <= 1 and text.strip():
        parts = re.split(r"\s+(?=(?:\[\d+\]|\d+\.|\d+\))\s+)", _clean_text(text))
        parsed = []
        for part in parts:
            match = _REFERENCE_START_RE.match(part.strip())
            parsed.append((match.group("label").strip("[]().-") if match else None, match.group("body").strip() if match else part.strip()))
        return [(label, body) for label, body in parsed if body]
    return [(label, _strip_reference_label(" ".join(parts))) for label, parts in entries if " ".join(parts).strip()]


def _strip_reference_label(text: str) -> str:
    return re.sub(r"^(?:\[\d+\]|\d+\.|\d+\)|[-*])\s*", "", text).strip()


def _extract_reference_authors(text: str) -> list[str]:
    match = re.match(
        r"^(?P<authors>(?:(?:[A-Z]\.\s*)*[A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+)?)(?:\s*(?:,|and|&)\s*(?:[A-Z]\.\s*)*[A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+)?)*)\.\s+",
        text,
    )
    if match is None:
        return []
    author_segment = match.group("authors").strip()
    if not author_segment or len(author_segment) > 300:
        return []
    authors = [part.strip() for part in re.split(r"\s+(?:and|&)\s+|,\s*", author_segment) if part.strip()]
    return authors[:20]


def _extract_reference_title(text: str, authors: list[str]) -> str | None:
    quote_match = _TITLE_QUOTE_RE.search(text)
    if quote_match:
        return quote_match.group("title").strip().rstrip(".")
    remainder = text
    if authors and "." in remainder:
        remainder = remainder.split(".", 1)[1].strip()
    sentences = [part.strip() for part in re.split(r"\.\s+", remainder) if part.strip()]
    for sentence in sentences:
        cleaned = re.sub(r"\b(?:In )?(?:Proceedings|Proc\.|Journal|Conference|arXiv|doi:)\b.*", "", sentence, flags=re.IGNORECASE).strip(" .")
        if 8 <= len(cleaned) <= 300 and not _DOI_RE.search(cleaned) and not _URL_RE.search(cleaned):
            return cleaned
    return None


def _extract_reference_source(
    text: str,
    title: str | None,
    authors: list[str],
    year: int | None,
    doi: str | None,
    arxiv_id: str | None,
    url: str | None,
) -> tuple[str | None, str | None]:
    remaining = text
    for value in [title, str(year) if year else None, doi, arxiv_id, url, *authors]:
        if value:
            remaining = remaining.replace(value, " ")
    remaining = re.sub(r"\b(?:DOI|doi|arXiv)\s*:?\s*", " ", remaining)
    remaining = _clean_text(remaining).strip(" .,-")
    source = None
    source_match = re.search(r"\b(?:In\s+)?((?:Proceedings|Proc\.|Journal|Conference|Transactions|arXiv)[^.]{3,160})", text, flags=re.IGNORECASE)
    if source_match:
        source = source_match.group(1).strip(" .,")
    return source, remaining or None


def _extract_year(text: str) -> int | None:
    match = _YEAR_RE.search(text)
    return int(match.group(1)) if match else None


def _reference_confidence(title: str | None, authors: list[str], doi: str | None, arxiv_id: str | None, url: str | None) -> float:
    score = 0.35
    if title:
        score += 0.2
    if authors:
        score += 0.15
    if doi or arxiv_id:
        score += 0.2
    elif url:
        score += 0.1
    return min(score, 0.95)


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
