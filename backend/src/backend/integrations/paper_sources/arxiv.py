from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import arxiv
import httpx

from backend.integrations.paper_sources.base import PaperSourceSearchResponse
from backend.schemas import PaperSearchResult
from backend.services.papers import normalize_identifier

_ARXIV_ID_RE = re.compile(r"(?:arxiv:\s*|arxiv\.org/(?:abs|pdf)/)?(?P<id>\d{4}\.\d{4,5}(?:v\d+)?)", re.IGNORECASE)
_DOI_PREFIX_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)


@dataclass
class ArxivRateLimiter:
    min_interval_seconds: float = 3.0
    monotonic: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    _last_call_at: float | None = None

    def wait(self) -> None:
        now = self.monotonic()
        if self._last_call_at is not None:
            remaining = self.min_interval_seconds - (now - self._last_call_at)
            if remaining > 0:
                self.sleep(remaining)
                now = self.monotonic()
        self._last_call_at = now


class ArxivClient:
    def __init__(
        self,
        *,
        limiter: ArxivRateLimiter | None = None,
        max_retries: int = 3,
        backoff_base_seconds: float = 1.0,
        backoff_max_seconds: float = 30.0,
        timeout_seconds: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
        arxiv_client: arxiv.Client | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.limiter = limiter or ArxivRateLimiter()
        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds
        self.backoff_max_seconds = backoff_max_seconds
        self.sleep = sleep
        self.arxiv_client = arxiv_client or arxiv.Client(page_size=25, delay_seconds=limiter.min_interval_seconds if limiter is not None else 3.0, num_retries=0)
        self.http_client = http_client or httpx.Client(follow_redirects=True, timeout=timeout_seconds)

    def search(self, query: str, max_results: int = 10, *, mode: str = "auto", offset: int = 0) -> PaperSourceSearchResponse:
        warnings: list[str] = []
        max_results = max(1, min(max_results, 25))
        offset = max(0, offset)
        query_used, id_list = _arxiv_query(query, mode, warnings)
        if _is_broad_query(query, mode):
            warnings.append("Broad arXiv query; refine with title terms, author, year, category, or identifier before paging broadly.")
        search = arxiv.Search(
            query="" if id_list else query_used,
            id_list=id_list,
            max_results=max_results + offset,
            sort_by=arxiv.SortCriterion.Relevance,
        )
        results = self._with_retry(lambda: list(self.arxiv_client.results(search)))
        if offset:
            results = results[offset:]
        return PaperSourceSearchResponse(results=[self._to_search_result(result) for result in results[:max_results]], query_used=query_used, warnings=warnings)

    def download_pdf(self, pdf_url: str, destination: Path) -> Path:
        return self._download(pdf_url, destination)

    def download_source(self, arxiv_id: str, destination: Path) -> Path:
        normalized_id = normalize_arxiv_id(arxiv_id)
        return self._download(f"https://arxiv.org/src/{normalized_id}", destination)

    def _download(self, url: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)

        def fetch() -> httpx.Response:
            response = self.http_client.get(url)
            response.raise_for_status()
            return response

        response = self._with_retry(fetch)
        destination.write_bytes(response.content)
        return destination

    def _with_retry(self, operation: Callable[[], Any]) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self.limiter.wait()
            try:
                return operation()
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                self.sleep(min(self.backoff_max_seconds, self.backoff_base_seconds * (2**attempt)))
        raise last_error or RuntimeError("arXiv operation failed")

    def _to_search_result(self, result: arxiv.Result) -> PaperSearchResult:
        arxiv_id = result.get_short_id()
        doi = result.doi.strip() if result.doi else None
        return PaperSearchResult(
            source="arxiv",
            source_record_id=arxiv_id,
            title=result.title,
            abstract=result.summary,
            authors=[author.name for author in result.authors],
            year=result.published.year if result.published else None,
            venue="arXiv",
            doi=doi,
            arxiv_id=arxiv_id,
            landing_page_url=result.entry_id,
            pdf_url=result.pdf_url,
            raw={
                "entry_id": result.entry_id,
                "primary_category": result.primary_category,
                "categories": result.categories,
                "published": result.published.isoformat() if result.published else None,
                "updated": result.updated.isoformat() if result.updated else None,
            },
        )


def normalize_arxiv_id(value: str) -> str:
    arxiv_id = _extract_arxiv_id(value)
    if arxiv_id is not None:
        return arxiv_id
    parsed = urlparse(value.strip())
    candidate = parsed.path.strip("/").split("/")[-1] if parsed.scheme and parsed.netloc else value.strip()
    candidate = candidate.removesuffix(".pdf")
    normalized = normalize_identifier("arxiv", candidate)
    if not normalized or not re.fullmatch(r"\d{4}\.\d{4,5}", normalized):
        raise ValueError(f"Invalid arXiv id: {value}")
    return normalized


def _arxiv_query(query: str, mode: str, warnings: list[str]) -> tuple[str, list[str] | None]:
    stripped = query.strip()
    normalized_mode = mode.lower()
    if normalized_mode in {"arxiv_id", "identifier"}:
        arxiv_id = _extract_arxiv_id(stripped)
        if arxiv_id is not None:
            return f"id_list:{arxiv_id}", [arxiv_id]
    if normalized_mode == "auto":
        arxiv_id = _extract_arxiv_id(stripped)
        if arxiv_id is not None:
            return f"id_list:{arxiv_id}", [arxiv_id]
    if normalized_mode == "doi":
        doi = _DOI_PREFIX_RE.sub("", stripped).strip().rstrip(".").lower()
        warnings.append("arXiv DOI search can be incomplete; use OpenAlex DOI search when exact DOI matching is required.")
        return f'doi:"{doi}"', None
    if normalized_mode == "title":
        return f'ti:"{stripped}"', None
    if normalized_mode == "keyword":
        return f'all:"{stripped}"', None
    if normalized_mode == "advanced":
        return stripped, None
    return stripped, None


def _extract_arxiv_id(value: str) -> str | None:
    match = _ARXIV_ID_RE.search(value)
    if match is None:
        return None
    return normalize_identifier("arxiv", match.group("id"))


def _is_broad_query(query: str, mode: str) -> bool:
    if mode not in {"auto", "keyword"}:
        return False
    terms = [term for term in re.split(r"\W+", query.strip()) if term]
    return len(terms) <= 2 or len(query.strip()) < 12
