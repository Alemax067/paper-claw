from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.api.deps import get_db_session
from backend.api.serializers import arxiv_task_category_read, arxiv_task_daily_config_read, arxiv_task_job_read, arxiv_task_paper_read, arxiv_task_status_read, arxiv_task_window_read
from backend.db.repositories import ArxivTaskRepository
from backend.schemas import (
    ArxivTaskCategoryRead,
    ArxivTaskCategoryUpdateRequest,
    ArxivTaskDailyConfigRead,
    ArxivTaskDailyConfigUpdateRequest,
    ArxivTaskHarvestJobRead,
    ArxivTaskHistoryJobCreateRequest,
    ArxivTaskPaperRead,
    ArxivTaskQueryWindowRead,
    ArxivTaskStatusRead,
)
from backend.services.arxiv_task_scheduler import poke_arxiv_task_scheduler
from backend.services.arxiv_tasks import ArxivTaskService

router = APIRouter(tags=["tasks"])


@router.get("/tasks/arxiv/status", response_model=ArxivTaskStatusRead)
def get_arxiv_task_status(session: Session = Depends(get_db_session)) -> ArxivTaskStatusRead:
    repository = ArxivTaskRepository(session)
    categories = repository.list_categories()
    return arxiv_task_status_read(
        daily_config=repository.daily_config(),
        categories=categories,
        coverage_cat_ids=repository.successful_cat_ids_with_papers(),
        active_job=repository.running_job(),
        recent_jobs=repository.list_jobs(limit=20),
        recent_windows=repository.list_windows(limit=100),
        recent_papers=repository.list_papers(limit=20),
        total_papers=repository.count_papers(),
    )


@router.get("/tasks/arxiv/daily-config", response_model=ArxivTaskDailyConfigRead)
def get_arxiv_daily_config(session: Session = Depends(get_db_session)) -> ArxivTaskDailyConfigRead:
    return arxiv_task_daily_config_read(ArxivTaskRepository(session).daily_config())


@router.put("/tasks/arxiv/daily-config", response_model=ArxivTaskDailyConfigRead)
def update_arxiv_daily_config(request: ArxivTaskDailyConfigUpdateRequest, session: Session = Depends(get_db_session)) -> ArxivTaskDailyConfigRead:
    if not _valid_run_time(request.run_time):
        raise HTTPException(status_code=400, detail="run_time must use HH:MM format")
    config = ArxivTaskRepository(session).update_daily_config(enabled=request.enabled, run_time=request.run_time)
    session.commit()
    return arxiv_task_daily_config_read(config)


@router.get("/tasks/arxiv/categories", response_model=list[ArxivTaskCategoryRead])
def list_arxiv_task_categories(session: Session = Depends(get_db_session)) -> list[ArxivTaskCategoryRead]:
    return [arxiv_task_category_read(category) for category in ArxivTaskRepository(session).list_categories()]


@router.put("/tasks/arxiv/categories", response_model=list[ArxivTaskCategoryRead])
def update_arxiv_task_categories(request: ArxivTaskCategoryUpdateRequest, session: Session = Depends(get_db_session)) -> list[ArxivTaskCategoryRead]:
    try:
        categories = ArxivTaskService(session).update_categories(request.enabled_cat_ids)
        session.commit()
        return [arxiv_task_category_read(category) for category in categories]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/tasks/arxiv/daily/run", response_model=ArxivTaskHarvestJobRead)
def run_arxiv_daily_now(background_tasks: BackgroundTasks, session: Session = Depends(get_db_session)) -> ArxivTaskHarvestJobRead:
    try:
        job = ArxivTaskService(session).run_daily_once()
        session.commit()
        background_tasks.add_task(poke_arxiv_task_scheduler)
        return arxiv_task_job_read(job)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/tasks/arxiv/history-jobs", response_model=ArxivTaskHarvestJobRead)
def create_arxiv_history_job(request: ArxivTaskHistoryJobCreateRequest, session: Session = Depends(get_db_session)) -> ArxivTaskHarvestJobRead:
    try:
        job = ArxivTaskService(session).create_history_job(request.cat_ids, request.start_time, request.end_time)
        session.commit()
        return arxiv_task_job_read(job)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/tasks/arxiv/history-jobs/{job_id}/start", response_model=ArxivTaskHarvestJobRead)
def start_arxiv_history_job(job_id: int, background_tasks: BackgroundTasks, session: Session = Depends(get_db_session)) -> ArxivTaskHarvestJobRead:
    try:
        job = ArxivTaskService(session).start_job(job_id)
        session.commit()
        background_tasks.add_task(poke_arxiv_task_scheduler)
        return arxiv_task_job_read(job)
    except ValueError as exc:
        raise HTTPException(status_code=400 if "not found" not in str(exc).lower() else 404, detail=str(exc)) from exc


@router.post("/tasks/arxiv/history-jobs/{job_id}/pause", response_model=ArxivTaskHarvestJobRead)
def pause_arxiv_history_job(job_id: int, session: Session = Depends(get_db_session)) -> ArxivTaskHarvestJobRead:
    try:
        job = ArxivTaskService(session).pause_job(job_id)
        session.commit()
        return arxiv_task_job_read(job)
    except ValueError as exc:
        raise HTTPException(status_code=400 if "not found" not in str(exc).lower() else 404, detail=str(exc)) from exc


@router.post("/tasks/arxiv/history-jobs/{job_id}/stop", response_model=ArxivTaskHarvestJobRead)
def stop_arxiv_history_job(job_id: int, session: Session = Depends(get_db_session)) -> ArxivTaskHarvestJobRead:
    try:
        job = ArxivTaskService(session).stop_job(job_id)
        session.commit()
        return arxiv_task_job_read(job)
    except ValueError as exc:
        raise HTTPException(status_code=400 if "not found" not in str(exc).lower() else 404, detail=str(exc)) from exc


@router.get("/tasks/arxiv/windows", response_model=list[ArxivTaskQueryWindowRead])
def list_arxiv_task_windows(cat_id: str | None = None, limit: int = Query(default=100, ge=1, le=500), session: Session = Depends(get_db_session)) -> list[ArxivTaskQueryWindowRead]:
    return [arxiv_task_window_read(window) for window in ArxivTaskRepository(session).list_windows(cat_id=cat_id, limit=limit)]


@router.get("/tasks/arxiv/papers", response_model=list[ArxivTaskPaperRead])
def list_arxiv_task_papers(cat_id: str | None = None, limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0), session: Session = Depends(get_db_session)) -> list[ArxivTaskPaperRead]:
    return [arxiv_task_paper_read(paper) for paper in ArxivTaskRepository(session).list_papers(cat_id=cat_id, limit=limit, offset=offset)]


def _valid_run_time(value: str) -> bool:
    parts = value.split(":")
    if len(parts) != 2:
        return False
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return False
    return 0 <= hour <= 23 and 0 <= minute <= 59 and len(parts[0]) == 2 and len(parts[1]) == 2
