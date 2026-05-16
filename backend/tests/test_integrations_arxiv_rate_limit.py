from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from backend.integrations.paper_sources.arxiv import ArxivClient, ArxivRateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_arxiv_rate_limiter_defaults_to_three_seconds():
    assert ArxivRateLimiter().min_interval_seconds == 3.0


def test_arxiv_rate_limiter_waits_between_calls():
    clock = FakeClock()
    limiter = ArxivRateLimiter(min_interval_seconds=3.0, monotonic=clock.monotonic, sleep=clock.sleep)

    limiter.wait()
    limiter.wait()

    assert clock.sleeps == [3.0]


def test_arxiv_search_and_download_share_limiter(tmp_path):
    clock = FakeClock()
    limiter = ArxivRateLimiter(min_interval_seconds=1.0, monotonic=clock.monotonic, sleep=clock.sleep)
    result = SimpleNamespace(
        get_short_id=lambda: "2401.00001",
        doi=None,
        title="Shared limiter paper",
        summary="abstract",
        authors=[SimpleNamespace(name="A")],
        published=datetime(2024, 1, 1, tzinfo=UTC),
        updated=datetime(2024, 1, 2, tzinfo=UTC),
        primary_category="cs.AI",
        categories=["cs.AI"],
        entry_id="https://arxiv.org/abs/2401.00001",
        pdf_url="https://arxiv.org/pdf/2401.00001",
    )
    fake_arxiv_client = SimpleNamespace(results=lambda search: [result])
    fake_response = SimpleNamespace(content=b"pdf", raise_for_status=lambda: None)
    requested_urls = []
    fake_http_client = SimpleNamespace(get=lambda url: requested_urls.append(url) or fake_response)
    client = ArxivClient(
        limiter=limiter,
        sleep=clock.sleep,
        arxiv_client=fake_arxiv_client,
        http_client=fake_http_client,
    )

    client.search("rag")
    client.download_pdf("https://arxiv.org/pdf/2401.00001", tmp_path / "paper.pdf")
    client.download_source("2401.00001v2", tmp_path / "source.tar.gz")

    assert clock.sleeps == [1.0, 1.0]
    assert requested_urls[-1] == "https://arxiv.org/src/2401.00001"
    assert "/e-print/" not in requested_urls[-1]


def test_arxiv_retry_uses_exponential_backoff():
    clock = FakeClock()
    limiter = ArxivRateLimiter(min_interval_seconds=1.0, monotonic=clock.monotonic, sleep=clock.sleep)
    calls = {"count": 0}

    def operation():
        calls["count"] += 1
        if calls["count"] < 3:
            raise RuntimeError("transient")
        return "ok"

    client = ArxivClient(limiter=limiter, max_retries=3, backoff_base_seconds=2.0, backoff_max_seconds=5.0, sleep=clock.sleep)

    assert client._with_retry(operation) == "ok"
    assert clock.sleeps == [2.0, 4.0]


def test_arxiv_retry_reraises_last_error():
    clock = FakeClock()
    limiter = ArxivRateLimiter(min_interval_seconds=1.0, monotonic=clock.monotonic, sleep=clock.sleep)
    client = ArxivClient(limiter=limiter, max_retries=1, sleep=clock.sleep)

    with pytest.raises(RuntimeError, match="boom"):
        client._with_retry(lambda: (_ for _ in ()).throw(RuntimeError("boom")))


def test_arxiv_id_mode_uses_exact_id_lookup():
    captured = []
    fake_arxiv_client = SimpleNamespace(results=lambda search: captured.append(search) or [])
    client = ArxivClient(limiter=ArxivRateLimiter(min_interval_seconds=0), arxiv_client=fake_arxiv_client)

    response = client.search("https://arxiv.org/abs/2401.00001v2", mode="arxiv_id")

    assert response.query_used == "id_list:2401.00001"
    assert captured[0].id_list == ["2401.00001"]


def test_arxiv_offset_and_max_results_are_applied():
    results = [
        SimpleNamespace(
            get_short_id=lambda index=index: f"2401.0000{index}",
            doi=None,
            title=f"Paper {index}",
            summary="abstract",
            authors=[],
            published=datetime(2024, 1, 1, tzinfo=UTC),
            updated=datetime(2024, 1, 2, tzinfo=UTC),
            primary_category="cs.AI",
            categories=["cs.AI"],
            entry_id=f"https://arxiv.org/abs/2401.0000{index}",
            pdf_url=f"https://arxiv.org/pdf/2401.0000{index}",
        )
        for index in range(30)
    ]
    captured = []
    fake_arxiv_client = SimpleNamespace(results=lambda search: captured.append(search) or results)
    client = ArxivClient(limiter=ArxivRateLimiter(min_interval_seconds=0), arxiv_client=fake_arxiv_client)

    response = client.search("agent", max_results=100, mode="keyword", offset=2)

    assert captured[0].max_results == 27
    assert len(response.results) == 25
    assert response.results[0].title == "Paper 2"
    assert response.warnings
