from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.models import ArxivTaskCategory, ArxivTaskDailyConfig, ArxivTaskHarvestJob, ArxivTaskPaper, ArxivTaskPaperCategory, ArxivTaskQueryWindow
from backend.db.types import ArxivTaskDailyStatus, ArxivTaskJobKind, ArxivTaskJobStatus, ArxivTaskWindowStatus


class ArxivTaskRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def daily_config(self) -> ArxivTaskDailyConfig:
        config = self.session.scalar(select(ArxivTaskDailyConfig).order_by(ArxivTaskDailyConfig.id).limit(1))
        if config is None:
            config = ArxivTaskDailyConfig(status=ArxivTaskDailyStatus.enabled.value, run_time="08:00", metadata_json={})
            self.session.add(config)
            self.session.flush()
        return config

    def update_daily_config(self, *, enabled: bool, run_time: str) -> ArxivTaskDailyConfig:
        config = self.daily_config()
        config.status = ArxivTaskDailyStatus.enabled.value if enabled else ArxivTaskDailyStatus.disabled.value
        config.run_time = run_time
        self.session.flush()
        return config

    def list_categories(self) -> list[ArxivTaskCategory]:
        return list(
            self.session.scalars(
                select(ArxivTaskCategory).order_by(
                    ArxivTaskCategory.top_area,
                    ArxivTaskCategory.group,
                    ArxivTaskCategory.group_code,
                    ArxivTaskCategory.archive,
                    ArxivTaskCategory.cat_id,
                )
            )
        )

    def enabled_categories(self) -> list[ArxivTaskCategory]:
        return list(self.session.scalars(select(ArxivTaskCategory).where(ArxivTaskCategory.enabled.is_(True)).order_by(ArxivTaskCategory.cat_id)))

    def update_enabled_categories(self, enabled_cat_ids: list[str]) -> list[ArxivTaskCategory]:
        enabled = set(enabled_cat_ids)
        categories = self.list_categories()
        known = {category.cat_id for category in categories}
        unknown = sorted(enabled - known)
        if unknown:
            raise ValueError(f"Unknown arXiv categories: {', '.join(unknown)}")
        for category in categories:
            category.enabled = category.cat_id in enabled
        self.session.flush()
        return categories

    def create_job(self, kind: str, cat_ids: list[str], **values: Any) -> ArxivTaskHarvestJob:
        job = ArxivTaskHarvestJob(kind=kind, cat_ids_json=cat_ids, **values)
        self.session.add(job)
        self.session.flush()
        return job

    def list_jobs(self, *, limit: int = 20) -> list[ArxivTaskHarvestJob]:
        return list(self.session.scalars(select(ArxivTaskHarvestJob).order_by(ArxivTaskHarvestJob.created_at.desc()).limit(limit)))

    def running_job(self) -> ArxivTaskHarvestJob | None:
        return self.session.scalar(select(ArxivTaskHarvestJob).where(ArxivTaskHarvestJob.status == ArxivTaskJobStatus.running.value).order_by(ArxivTaskHarvestJob.updated_at.desc()))

    def list_running_history_jobs(self) -> list[ArxivTaskHarvestJob]:
        return list(
            self.session.scalars(
                select(ArxivTaskHarvestJob)
                .where(ArxivTaskHarvestJob.kind == ArxivTaskJobKind.history.value, ArxivTaskHarvestJob.status == ArxivTaskJobStatus.running.value)
                .order_by(ArxivTaskHarvestJob.updated_at)
            )
        )

    def create_window(self, cat_id: str, window_start: datetime, window_end: datetime, **values: Any) -> ArxivTaskQueryWindow:
        window = ArxivTaskQueryWindow(cat_id=cat_id, window_start=window_start, window_end=window_end, **values)
        self.session.add(window)
        self.session.flush()
        return window

    def list_windows(self, *, cat_id: str | None = None, limit: int = 100) -> list[ArxivTaskQueryWindow]:
        statement = select(ArxivTaskQueryWindow).order_by(ArxivTaskQueryWindow.window_start.desc(), ArxivTaskQueryWindow.id.desc()).limit(limit)
        if cat_id is not None:
            statement = statement.where(ArxivTaskQueryWindow.cat_id == cat_id)
        return list(self.session.scalars(statement))

    def successful_cat_ids_with_papers(self) -> list[str]:
        rows = self.session.execute(select(ArxivTaskPaperCategory.cat_id).distinct().order_by(ArxivTaskPaperCategory.cat_id)).all()
        return [row[0] for row in rows]

    def latest_successful_window_end(self, cat_id: str) -> datetime | None:
        return self.session.scalar(
            select(func.max(ArxivTaskQueryWindow.window_end)).where(
                ArxivTaskQueryWindow.cat_id == cat_id,
                ArxivTaskQueryWindow.status == ArxivTaskWindowStatus.succeeded.value,
            )
        )

    def list_papers(self, *, cat_id: str | None = None, limit: int = 50, offset: int = 0) -> list[ArxivTaskPaper]:
        statement = select(ArxivTaskPaper).order_by(ArxivTaskPaper.published_at.desc().nullslast(), ArxivTaskPaper.id.desc()).limit(limit).offset(offset)
        if cat_id is not None:
            statement = statement.join(ArxivTaskPaperCategory).where(ArxivTaskPaperCategory.cat_id == cat_id)
        return list(self.session.scalars(statement))

    def count_papers(self) -> int:
        return int(self.session.scalar(select(func.count(ArxivTaskPaper.id))) or 0)

    def upsert_paper(self, *, arxiv_base_id: str, values: dict[str, Any], now: datetime) -> tuple[ArxivTaskPaper, bool]:
        paper = self.session.scalar(select(ArxivTaskPaper).where(ArxivTaskPaper.arxiv_base_id == arxiv_base_id))
        inserted = paper is None
        if paper is None:
            paper = ArxivTaskPaper(arxiv_base_id=arxiv_base_id, first_seen_at=now, last_seen_at=now, **values)
            self.session.add(paper)
        else:
            for key, value in values.items():
                setattr(paper, key, value)
            paper.last_seen_at = now
        self.session.flush()
        return paper, inserted

    def upsert_paper_category(self, paper_id: int, cat_id: str, *, is_primary: bool = False) -> ArxivTaskPaperCategory:
        link = self.session.scalar(select(ArxivTaskPaperCategory).where(ArxivTaskPaperCategory.paper_id == paper_id, ArxivTaskPaperCategory.cat_id == cat_id))
        if link is None:
            link = ArxivTaskPaperCategory(paper_id=paper_id, cat_id=cat_id, is_primary=is_primary, created_at=datetime.now().astimezone())
            self.session.add(link)
        else:
            link.is_primary = link.is_primary or is_primary
        self.session.flush()
        return link
