from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import arxiv
import httpx

from backend.schemas import PaperSearchResult


@dataclass
class ArxivRateLimiter:
    min_interval_seconds: float = 1.0
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
        sleep: Callable[[float], None] = time.sleep,
        arxiv_client: arxiv.Client | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.limiter = limiter or ArxivRateLimiter()
        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds
        self.backoff_max_seconds = backoff_max_seconds
        self.sleep = sleep
        self.arxiv_client = arxiv_client or arxiv.Client()
        self.http_client = http_client or httpx.Client(follow_redirects=True, timeout=30)

    def search(self, query: str, max_results: int = 10) -> list[PaperSearchResult]:
        max_results = max(1, min(max_results, 50))
        search = arxiv.Search(query=query, max_results=max_results, sort_by=arxiv.SortCriterion.Relevance)
        results = self._with_retry(lambda: list(self.arxiv_client.results(search)))
        return [self._to_search_result(result) for result in results]

    def download_pdf(self, pdf_url: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)

        def fetch() -> httpx.Response:
            response = self.http_client.get(pdf_url)
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
