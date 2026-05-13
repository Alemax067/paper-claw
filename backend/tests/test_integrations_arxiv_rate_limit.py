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


def test_arxiv_rate_limiter_waits_between_calls():
    clock = FakeClock()
    limiter = ArxivRateLimiter(min_interval_seconds=1.0, monotonic=clock.monotonic, sleep=clock.sleep)

    limiter.wait()
    limiter.wait()

    assert clock.sleeps == [1.0]


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
    fake_http_client = SimpleNamespace(get=lambda url: fake_response)
    client = ArxivClient(
        limiter=limiter,
        sleep=clock.sleep,
        arxiv_client=fake_arxiv_client,
        http_client=fake_http_client,
    )

    client.search("rag")
    client.download_pdf("https://arxiv.org/pdf/2401.00001", tmp_path / "paper.pdf")

    assert clock.sleeps == [1.0]


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
