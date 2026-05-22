from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from backend.db.models import ArxivTaskCategory
from backend.db.types import ArxivTaskJobKind, ArxivTaskJobStatus, ArxivTaskWindowStatus
from backend.integrations.paper_sources.arxiv import ArxivMetadataEntry, ArxivMetadataQueryResponse
from backend.services.arxiv_tasks import ArxivTaskService


@dataclass
class FakeMetadataClient:
    total_results: int = 1
    calls: list[tuple[str, datetime, datetime, int, int]] | None = None
    on_call: Callable[[], None] | None = None

    def query_metadata_window(self, cat_id: str, start_time: datetime, end_time: datetime, *, page_size: int = 100, offset: int = 0):
        if self.calls is None:
            self.calls = []
        self.calls.append((cat_id, start_time, end_time, page_size, offset))
        if self.on_call is not None:
            self.on_call()
        entry = ArxivMetadataEntry(
            arxiv_id="2401.00001v1",
            arxiv_base_id="2401.00001",
            title="A harvested paper",
            abstract="abstract",
            authors=["Ada Lovelace"],
            primary_category=cat_id,
            categories=[cat_id, "cs.AI"],
            published_at=start_time + timedelta(minutes=5),
            updated_at=end_time,
            landing_page_url="https://arxiv.org/abs/2401.00001v1",
            pdf_url="https://arxiv.org/pdf/2401.00001v1",
            doi=None,
            journal_ref=None,
            comment=None,
            raw={"id": "2401.00001v1"},
        )
        return ArxivMetadataQueryResponse(
            query_used="cat:cs.LG",
            total_results=self.total_results,
            start=offset,
            page_size=page_size,
            entries=[] if offset else [entry],
        )


def test_harvest_window_upserts_task_metadata_without_curated_papers(session):
    client = FakeMetadataClient()
    service = ArxivTaskService(session, arxiv_client=client)
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=1)

    stats = service.harvest_window("cs.LG", start, end, job_id=None, kind=ArxivTaskJobKind.history.value)
    second_stats = service.harvest_window("cs.LG", start, end, job_id=None, kind=ArxivTaskJobKind.history.value)
    session.commit()

    assert stats.inserted_count == 1
    assert second_stats.updated_count == 1
    assert session.execute(text("select count(*) from arxiv_task_papers")).scalar_one() == 1
    assert session.execute(text("select count(*) from papers")).scalar_one() == 0


def test_harvest_window_splits_large_result_windows(session):
    client = FakeMetadataClient(total_results=1001)
    service = ArxivTaskService(session, arxiv_client=client)
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=2)

    service.harvest_window("cs.LG", start, end, job_id=None, kind=ArxivTaskJobKind.history.value)
    session.commit()

    windows = session.execute(text("select status from arxiv_task_query_windows order by id")).scalars().all()
    assert windows[0] == ArxivTaskWindowStatus.split.value
    assert windows.count(ArxivTaskWindowStatus.partial.value) == 2


def test_run_history_step_honors_stop_after_current_window(session):
    session.add(ArxivTaskCategory(cat_id="cs.LG", top_area="Computer Science", group=None, group_code=None, archive="cs", name="Machine Learning", is_alias=False, alias_of=None, api_exact_query="cat:cs.LG", enabled=False))
    session.commit()
    service = ArxivTaskService(session, arxiv_client=FakeMetadataClient(total_results=0))
    job = service.create_history_job(["cs.LG"], datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 2, tzinfo=UTC))
    service.start_job(job.id)

    def stop_during_window() -> None:
        session.execute(text("update arxiv_task_harvest_jobs set status = 'stopping' where id = :job_id"), {"job_id": job.id})
        session.commit()

    service.arxiv_client.on_call = stop_during_window
    service.run_history_step(job.id)
    session.commit()

    assert job.status == ArxivTaskJobStatus.stopped.value


def test_daily_uses_latest_successful_coverage(session):
    category = ArxivTaskCategory(cat_id="cs.LG", top_area="Computer Science", group=None, group_code=None, archive="cs", name="Machine Learning", is_alias=False, alias_of=None, api_exact_query="cat:cs.LG", enabled=True)
    session.add(category)
    session.commit()
    client = FakeMetadataClient(total_results=0)
    service = ArxivTaskService(session, arxiv_client=client)

    job = service.run_daily_once()
    session.commit()

    assert job.status == ArxivTaskJobStatus.succeeded.value
    assert client.calls is not None
    assert all(end - start <= timedelta(days=1) for _, start, end, _, _ in client.calls)
