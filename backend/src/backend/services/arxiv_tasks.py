from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy.orm import Session

from backend.db.models import ArxivTaskHarvestJob, ArxivTaskQueryWindow
from backend.db.repositories import ArxivTaskRepository
from backend.db.types import ArxivTaskJobKind, ArxivTaskJobStatus, ArxivTaskWindowStatus
from backend.integrations.paper_sources.arxiv import ArxivClient, ArxivMetadataEntry
from backend.integrations.paper_sources.factory import paper_source_adapters_from_settings

PAGE_SIZE = 100
MAX_RESULTS_BEFORE_SPLIT = 1000
MIN_SPLIT_WINDOW = timedelta(hours=1)
MAX_WINDOW = timedelta(days=1)


class ArxivMetadataClient(Protocol):
    def query_metadata_window(self, cat_id: str, start_time: datetime, end_time: datetime, *, page_size: int = PAGE_SIZE, offset: int = 0): ...


@dataclass(frozen=True)
class HarvestStats:
    fetched_count: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    page_count: int = 0

    def add(self, other: HarvestStats) -> HarvestStats:
        return HarvestStats(
            fetched_count=self.fetched_count + other.fetched_count,
            inserted_count=self.inserted_count + other.inserted_count,
            updated_count=self.updated_count + other.updated_count,
            page_count=self.page_count + other.page_count,
        )


class ArxivTaskService:
    def __init__(self, session: Session, *, arxiv_client: ArxivMetadataClient | None = None) -> None:
        self.session = session
        self.repository = ArxivTaskRepository(session)
        self.arxiv_client = arxiv_client or _arxiv_client_from_settings()

    def update_categories(self, enabled_cat_ids: list[str]):
        return self.repository.update_enabled_categories(enabled_cat_ids)

    def create_history_job(self, cat_ids: list[str], start_time: datetime, end_time: datetime) -> ArxivTaskHarvestJob:
        self._validate_categories(cat_ids)
        start_time = _as_utc(start_time)
        end_time = _as_utc(end_time)
        if end_time <= start_time:
            raise ValueError("History job end_time must be after start_time")
        return self.repository.create_job(
            ArxivTaskJobKind.history.value,
            cat_ids,
            requested_start=start_time,
            requested_end=end_time,
            status=ArxivTaskJobStatus.paused.value,
            stats_json={},
        )

    def start_job(self, job_id: int) -> ArxivTaskHarvestJob:
        job = self.session.get(ArxivTaskHarvestJob, job_id)
        if job is None:
            raise ValueError("History job not found")
        if job.kind != ArxivTaskJobKind.history.value:
            raise ValueError("Only history jobs can be manually started")
        if job.status in {ArxivTaskJobStatus.succeeded.value, ArxivTaskJobStatus.stopped.value}:
            raise ValueError("History job cannot be started from its current status")
        now = _now()
        job.status = ArxivTaskJobStatus.running.value
        job.started_at = job.started_at or now
        job.finished_at = None
        job.error_message = None
        self.session.flush()
        return job

    def pause_job(self, job_id: int) -> ArxivTaskHarvestJob:
        job = self.session.get(ArxivTaskHarvestJob, job_id)
        if job is None:
            raise ValueError("History job not found")
        if job.kind != ArxivTaskJobKind.history.value:
            raise ValueError("Only history jobs can be paused")
        if job.status == ArxivTaskJobStatus.running.value:
            job.status = ArxivTaskJobStatus.paused.value
            self.session.flush()
        return job

    def stop_job(self, job_id: int) -> ArxivTaskHarvestJob:
        job = self.session.get(ArxivTaskHarvestJob, job_id)
        if job is None:
            raise ValueError("History job not found")
        if job.kind != ArxivTaskJobKind.history.value:
            raise ValueError("Only history jobs can be stopped")
        if job.status in {ArxivTaskJobStatus.running.value, ArxivTaskJobStatus.pending.value}:
            job.status = ArxivTaskJobStatus.stopping.value
        else:
            job.status = ArxivTaskJobStatus.stopped.value
            job.finished_at = _now()
        self.session.flush()
        return job

    def run_daily_once(self) -> ArxivTaskHarvestJob:
        categories = self.repository.enabled_categories()
        now = _now()
        config = self.repository.daily_config()
        config.last_started_at = now
        job = self.repository.create_job(
            ArxivTaskJobKind.daily.value,
            [category.cat_id for category in categories],
            status=ArxivTaskJobStatus.running.value,
            started_at=now,
            stats_json={},
        )
        total = HarvestStats()
        try:
            for category in categories:
                for start, end in self._daily_windows(category.cat_id, now):
                    total = total.add(self.harvest_window(category.cat_id, start, end, job_id=job.id, kind=ArxivTaskJobKind.daily.value))
            job.status = ArxivTaskJobStatus.succeeded.value
            job.stats_json = _stats_json(total)
            job.finished_at = _now()
            config.last_finished_at = job.finished_at
        except Exception as exc:
            job.status = ArxivTaskJobStatus.failed.value
            job.error_message = str(exc) or type(exc).__name__
            job.finished_at = _now()
            raise
        finally:
            self.session.flush()
        return job

    def run_history_step(self, job_id: int) -> ArxivTaskHarvestJob:
        job = self.session.get(ArxivTaskHarvestJob, job_id)
        if job is None:
            raise ValueError("History job not found")
        if job.status != ArxivTaskJobStatus.running.value:
            return job
        next_window = self._next_history_window(job)
        if next_window is None:
            job.status = ArxivTaskJobStatus.succeeded.value
            job.finished_at = _now()
            self.session.flush()
            return job
        cat_id, start, end = next_window
        try:
            stats = self.harvest_window(cat_id, start, end, job_id=job.id, kind=ArxivTaskJobKind.history.value)
            self.session.refresh(job)
            job.stats_json = _merge_stats(job.stats_json or {}, stats)
        except Exception as exc:
            job.status = ArxivTaskJobStatus.failed.value
            job.error_message = str(exc) or type(exc).__name__
            job.finished_at = _now()
            raise
        finally:
            if job.status == ArxivTaskJobStatus.stopping.value:
                job.status = ArxivTaskJobStatus.stopped.value
                job.finished_at = _now()
            self.session.flush()
        return job

    def harvest_window(self, cat_id: str, start_time: datetime, end_time: datetime, *, job_id: int | None, kind: str, parent_window_id: int | None = None) -> HarvestStats:
        start_time = _as_utc(start_time)
        end_time = _as_utc(end_time)
        if end_time <= start_time:
            raise ValueError("arXiv window end_time must be after start_time")
        if end_time - start_time > MAX_WINDOW:
            raise ValueError("arXiv window cannot exceed one day")
        window = self.repository.create_window(
            cat_id,
            start_time,
            end_time,
            job_id=job_id,
            kind=kind,
            parent_window_id=parent_window_id,
            status=ArxivTaskWindowStatus.running.value,
            started_at=_now(),
            page_size=PAGE_SIZE,
        )
        try:
            first_page = self.arxiv_client.query_metadata_window(cat_id, start_time, end_time, page_size=PAGE_SIZE, offset=0)
            window.total_results = first_page.total_results
            if first_page.total_results > MAX_RESULTS_BEFORE_SPLIT and end_time - start_time > MIN_SPLIT_WINDOW:
                middle = start_time + (end_time - start_time) / 2
                window.status = ArxivTaskWindowStatus.split.value
                window.finished_at = _now()
                self.session.flush()
                left = self.harvest_window(cat_id, start_time, middle, job_id=job_id, kind=kind, parent_window_id=window.id)
                right = self.harvest_window(cat_id, middle, end_time, job_id=job_id, kind=kind, parent_window_id=window.id)
                return left.add(right)
            stats = self._persist_pages(cat_id, first_page.entries, first_page.total_results, start_time, end_time)
            window.fetched_count = stats.fetched_count
            window.inserted_count = stats.inserted_count
            window.updated_count = stats.updated_count
            window.page_count = stats.page_count
            window.status = ArxivTaskWindowStatus.partial.value if first_page.total_results > MAX_RESULTS_BEFORE_SPLIT else ArxivTaskWindowStatus.succeeded.value
            if window.status == ArxivTaskWindowStatus.partial.value:
                window.warning_code = "too_many_results_min_window"
            window.finished_at = _now()
            self.session.flush()
            return stats
        except Exception as exc:
            window.status = ArxivTaskWindowStatus.failed.value
            window.error_message = str(exc) or type(exc).__name__
            window.finished_at = _now()
            self.session.flush()
            raise

    def _persist_pages(self, cat_id: str, first_entries: list[ArxivMetadataEntry], total_results: int, start_time: datetime, end_time: datetime) -> HarvestStats:
        total = self._persist_entries(cat_id, first_entries)
        page_count = 1
        offset = PAGE_SIZE
        while offset < total_results:
            page = self.arxiv_client.query_metadata_window(cat_id, start_time, end_time, page_size=PAGE_SIZE, offset=offset)
            total = total.add(self._persist_entries(cat_id, page.entries))
            page_count += 1
            offset += PAGE_SIZE
        return HarvestStats(total.fetched_count, total.inserted_count, total.updated_count, page_count)

    def _persist_entries(self, queried_cat_id: str, entries: list[ArxivMetadataEntry]) -> HarvestStats:
        now = _now()
        inserted = 0
        updated = 0
        for entry in entries:
            values = {
                "arxiv_id": entry.arxiv_id,
                "title": entry.title,
                "abstract": entry.abstract,
                "authors_json": entry.authors,
                "primary_category": entry.primary_category,
                "categories_json": entry.categories,
                "published_at": entry.published_at,
                "updated_at_source": entry.updated_at,
                "landing_page_url": entry.landing_page_url,
                "pdf_url": entry.pdf_url,
                "comment": entry.comment,
                "journal_ref": entry.journal_ref,
                "doi": entry.doi,
                "raw_json": entry.raw,
            }
            paper, was_inserted = self.repository.upsert_paper(arxiv_base_id=entry.arxiv_base_id, values=values, now=now)
            inserted += 1 if was_inserted else 0
            updated += 0 if was_inserted else 1
            self.repository.upsert_paper_category(paper.id, queried_cat_id, is_primary=entry.primary_category == queried_cat_id)
            for cat_id in entry.categories:
                self.repository.upsert_paper_category(paper.id, cat_id, is_primary=entry.primary_category == cat_id)
        return HarvestStats(fetched_count=len(entries), inserted_count=inserted, updated_count=updated, page_count=0)

    def _daily_windows(self, cat_id: str, end: datetime) -> list[tuple[datetime, datetime]]:
        start = self.repository.latest_successful_window_end(cat_id) or end - MAX_WINDOW
        start = _as_utc(start)
        if start >= end:
            return []
        windows = []
        cursor = start
        while cursor < end:
            next_end = min(cursor + MAX_WINDOW, end)
            windows.append((cursor, next_end))
            cursor = next_end
        return windows

    def _next_history_window(self, job: ArxivTaskHarvestJob) -> tuple[str, datetime, datetime] | None:
        if job.requested_start is None or job.requested_end is None:
            return None
        cat_ids = [str(cat_id) for cat_id in job.cat_ids_json or []]
        existing = {(window.cat_id, _as_utc(window.window_start), _as_utc(window.window_end)) for window in job.windows if window.status in {ArxivTaskWindowStatus.succeeded.value, ArxivTaskWindowStatus.partial.value, ArxivTaskWindowStatus.split.value}}
        for cat_id in cat_ids:
            cursor = _as_utc(job.requested_start)
            requested_end = _as_utc(job.requested_end)
            while cursor < requested_end:
                end = min(cursor + MAX_WINDOW, requested_end)
                key = (cat_id, cursor, end)
                if key not in existing:
                    return key
                cursor = end
        return None

    def _validate_categories(self, cat_ids: list[str]) -> None:
        known = {category.cat_id for category in self.repository.list_categories()}
        unknown = sorted(set(cat_ids) - known)
        if not cat_ids:
            raise ValueError("At least one arXiv category is required")
        if unknown:
            raise ValueError(f"Unknown arXiv categories: {', '.join(unknown)}")


def _arxiv_client_from_settings() -> ArxivClient:
    return paper_source_adapters_from_settings()["arxiv"]  # type: ignore[return-value]


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _stats_json(stats: HarvestStats) -> dict[str, int]:
    return {
        "fetched_count": stats.fetched_count,
        "inserted_count": stats.inserted_count,
        "updated_count": stats.updated_count,
        "page_count": stats.page_count,
    }


def _merge_stats(existing: dict[str, object], stats: HarvestStats) -> dict[str, int]:
    merged = dict(existing)
    for key, value in _stats_json(stats).items():
        merged[key] = int(merged.get(key, 0) or 0) + value
    return {key: int(value) for key, value in merged.items() if isinstance(value, int)}
