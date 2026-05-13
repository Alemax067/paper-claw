from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.models import Paper, PaperIdentifier, PaperSourceRecord
from backend.db.repositories import PaperRepository
from backend.db.types import IdentifierType, PaperSource
from backend.schemas import PaperIdentifierInput, PaperSearchResult

_DOI_PREFIX_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
_ARXIV_PREFIX_RE = re.compile(r"^(?:https?://arxiv\.org/(?:abs|pdf)/|arxiv:\s*)", re.IGNORECASE)
_OPENALEX_PREFIX_RE = re.compile(r"^https?://openalex\.org/", re.IGNORECASE)
_VERSION_SUFFIX_RE = re.compile(r"v\d+$", re.IGNORECASE)
_SPACE_RE = re.compile(r"\s+")


def normalize_identifier(identifier_type: str, value: str) -> str:
    value = value.strip()
    if identifier_type == IdentifierType.doi.value:
        value = _DOI_PREFIX_RE.sub("", value).strip().lower()
        return value.rstrip(".")
    if identifier_type == IdentifierType.arxiv.value:
        value = _ARXIV_PREFIX_RE.sub("", value).strip()
        value = value.removesuffix(".pdf")
        return _VERSION_SUFFIX_RE.sub("", value).lower()
    if identifier_type == IdentifierType.openalex.value:
        return _OPENALEX_PREFIX_RE.sub("", value).strip().upper()
    if identifier_type == IdentifierType.url.value:
        parsed = urlparse(value)
        if parsed.scheme and parsed.netloc:
            return parsed._replace(fragment="").geturl().rstrip("/")
    return value.strip()


def normalize_title(title: str) -> str:
    return _SPACE_RE.sub(" ", title).strip().lower()


def identifiers_from_search_result(result: PaperSearchResult) -> list[PaperIdentifierInput]:
    identifiers: list[PaperIdentifierInput] = []
    if result.doi:
        identifiers.append(PaperIdentifierInput(identifier_type=IdentifierType.doi.value, identifier_value=normalize_identifier(IdentifierType.doi.value, result.doi), is_primary=True))
    if result.arxiv_id:
        identifiers.append(PaperIdentifierInput(identifier_type=IdentifierType.arxiv.value, identifier_value=normalize_identifier(IdentifierType.arxiv.value, result.arxiv_id), is_primary=not identifiers))
    if result.openalex_id:
        identifiers.append(PaperIdentifierInput(identifier_type=IdentifierType.openalex.value, identifier_value=normalize_identifier(IdentifierType.openalex.value, result.openalex_id), is_primary=not identifiers))
    if result.landing_page_url:
        identifiers.append(PaperIdentifierInput(identifier_type=IdentifierType.url.value, identifier_value=normalize_identifier(IdentifierType.url.value, result.landing_page_url), is_primary=False))
    return _dedupe_identifiers(identifiers)


def find_paper_by_identifier(session: Session, identifier_type: str, identifier_value: str) -> Paper | None:
    normalized = normalize_identifier(identifier_type, identifier_value)
    return session.scalar(
        select(Paper)
        .join(PaperIdentifier)
        .where(
            PaperIdentifier.identifier_type == identifier_type,
            PaperIdentifier.identifier_value == normalized,
        )
    )


def search_papers_by_title(session: Session, title: str, limit: int = 10) -> list[Paper]:
    normalized = normalize_title(title)
    if not normalized:
        return []
    exact = list(session.scalars(select(Paper).where(func.lower(Paper.title) == normalized).limit(limit)))
    if exact:
        return exact
    terms = [term for term in normalized.split(" ") if len(term) >= 3][:6]
    if not terms:
        return []
    statement = select(Paper)
    for term in terms:
        statement = statement.where(Paper.title.ilike(f"%{term}%"))
    return list(session.scalars(statement.limit(limit)))


def upsert_paper_from_search_result(session: Session, result: PaperSearchResult) -> Paper:
    identifiers = identifiers_from_search_result(result)
    for identifier in identifiers:
        paper = find_paper_by_identifier(session, identifier.identifier_type, identifier.identifier_value)
        if paper is not None:
            _update_paper_metadata(paper, result)
            _upsert_paper_links(session, paper, result, identifiers)
            session.flush()
            return paper

    title_matches = search_papers_by_title(session, result.title, limit=1)
    if title_matches:
        paper = title_matches[0]
        _update_paper_metadata(paper, result)
    else:
        paper = PaperRepository(session).create(
            result.title,
            abstract=result.abstract,
            year=result.year,
            venue=result.venue,
            authors_json=result.authors,
            best_pdf_url=result.pdf_url,
            landing_page_url=result.landing_page_url,
            metadata_json={"source": result.source},
        )
    _upsert_paper_links(session, paper, result, identifiers)
    session.flush()
    return paper


def _update_paper_metadata(paper: Paper, result: PaperSearchResult) -> None:
    paper.title = result.title or paper.title
    paper.abstract = result.abstract or paper.abstract
    paper.year = result.year or paper.year
    paper.venue = result.venue or paper.venue
    paper.authors_json = result.authors or paper.authors_json
    paper.best_pdf_url = result.pdf_url or paper.best_pdf_url
    paper.landing_page_url = result.landing_page_url or paper.landing_page_url
    metadata = dict(paper.metadata_json or {})
    metadata.setdefault("source", result.source)
    paper.metadata_json = metadata


def _upsert_paper_links(session: Session, paper: Paper, result: PaperSearchResult, identifiers: list[PaperIdentifierInput]) -> None:
    repo = PaperRepository(session)
    for identifier in identifiers:
        repo.upsert_identifier(
            paper.id,
            identifier.identifier_type,
            identifier.identifier_value,
            is_primary=identifier.is_primary,
        )
    repo.upsert_source_record(
        paper.id,
        result.source,
        result.source_record_id,
        source_url=result.landing_page_url,
        retrieved_at=datetime.now().astimezone(),
        is_primary=result.source in {PaperSource.arxiv.value, PaperSource.openalex.value},
        raw_json=result.raw,
    )


def _dedupe_identifiers(identifiers: list[PaperIdentifierInput]) -> list[PaperIdentifierInput]:
    seen: set[tuple[str, str]] = set()
    deduped: list[PaperIdentifierInput] = []
    for identifier in identifiers:
        key = (identifier.identifier_type, identifier.identifier_value)
        if key not in seen:
            seen.add(key)
            deduped.append(identifier)
    return deduped
