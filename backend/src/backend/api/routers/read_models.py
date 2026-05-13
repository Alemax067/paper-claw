from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.api.deps import get_db_session
from backend.api.serializers import paper_detail, paper_summary, report_read, report_summary, run_read, search_session_read, thread_detail, thread_summary
from backend.db.models import AgentRun, Paper, PaperArtifact, Report, SearchSession, Thread
from backend.schemas import PaperDetail, PaperSummary, ReportRead, ReportSummary, RunRead, SearchSessionRead, ThreadDetail, ThreadSummary

router = APIRouter(tags=["read-models"])


@router.get("/threads", response_model=list[ThreadSummary])
def list_threads(session: Session = Depends(get_db_session)) -> list[ThreadSummary]:
    threads = session.scalars(select(Thread).order_by(Thread.updated_at.desc())).all()
    return [thread_summary(thread) for thread in threads]


@router.get("/threads/{thread_id}", response_model=ThreadDetail)
def get_thread(thread_id: int, session: Session = Depends(get_db_session)) -> ThreadDetail:
    thread = session.scalar(
        select(Thread)
        .where(Thread.id == thread_id)
        .options(selectinload(Thread.messages), selectinload(Thread.agent_runs).selectinload(AgentRun.events))
    )
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread_detail(thread)


@router.get("/runs/{run_id}", response_model=RunRead)
def get_run(run_id: int, session: Session = Depends(get_db_session)) -> RunRead:
    run = session.scalar(select(AgentRun).where(AgentRun.id == run_id).options(selectinload(AgentRun.events)))
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run_read(run)


@router.get("/papers", response_model=list[PaperSummary])
def list_papers(session: Session = Depends(get_db_session)) -> list[PaperSummary]:
    papers = session.scalars(select(Paper).order_by(Paper.updated_at.desc())).all()
    return [paper_summary(paper) for paper in papers]


@router.get("/papers/{paper_id}", response_model=PaperDetail)
def get_paper(paper_id: int, session: Session = Depends(get_db_session)) -> PaperDetail:
    paper = session.scalar(
        select(Paper)
        .where(Paper.id == paper_id)
        .options(
            selectinload(Paper.identifiers),
            selectinload(Paper.source_records),
            selectinload(Paper.paper_artifacts).selectinload(PaperArtifact.artifact),
            selectinload(Paper.parse_jobs),
            selectinload(Paper.processed_documents),
        )
    )
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    detail = paper_detail(paper)
    reports = session.scalars(select(Report).where(Report.paper_id == paper.id).order_by(Report.updated_at.desc())).all()
    detail.reports = [{"id": report.id, "title": report.title, "status": report.status, "report_type": report.report_type} for report in reports]
    return detail


@router.get("/search-sessions/{search_session_id}", response_model=SearchSessionRead)
def get_search_session(search_session_id: int, session: Session = Depends(get_db_session)) -> SearchSessionRead:
    search_session = session.scalar(select(SearchSession).where(SearchSession.id == search_session_id).options(selectinload(SearchSession.candidates)))
    if search_session is None:
        raise HTTPException(status_code=404, detail="Search session not found")
    return search_session_read(search_session)


@router.get("/reports", response_model=list[ReportSummary])
def list_reports(session: Session = Depends(get_db_session)) -> list[ReportSummary]:
    reports = session.scalars(select(Report).order_by(Report.updated_at.desc())).all()
    return [report_summary(report) for report in reports]


@router.get("/reports/{report_id}", response_model=ReportRead)
def get_report(report_id: int, session: Session = Depends(get_db_session)) -> ReportRead:
    report = session.scalar(select(Report).where(Report.id == report_id).options(selectinload(Report.evidence)))
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report_read(report)
