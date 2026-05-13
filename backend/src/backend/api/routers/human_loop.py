from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.deps import get_db_session
from backend.api.serializers import run_read, search_session_read
from backend.db.models import AgentRun, SearchSession
from backend.db.repositories import AgentRunRepository
from backend.db.types import EventLevel, RunStatus, SearchStatus
from backend.schemas import ApprovalRequest, ConfirmSearchCandidateRequest, RejectSearchSessionRequest, RunRead, SearchSessionRead
from backend.services.search import PaperSearchService

router = APIRouter(tags=["human-loop"])


@router.post("/search-sessions/{search_session_id}/confirm", response_model=SearchSessionRead)
def confirm_search_candidate(search_session_id: int, request: ConfirmSearchCandidateRequest, session: Session = Depends(get_db_session)) -> SearchSessionRead:
    search_session = PaperSearchService(session).confirm_candidate(
        search_session_id,
        request.candidate_id,
        update_thread_focus=request.update_thread_focus,
    )
    if search_session.run_id is not None:
        AgentRunRepository(session).append_event(
            search_session.run_id,
            "search_candidate_confirmed",
            payload_json={"search_session_id": search_session.id, "candidate_id": request.candidate_id},
        )
    return search_session_read(search_session)


@router.post("/search-sessions/{search_session_id}/reject", response_model=SearchSessionRead)
def reject_search_session(search_session_id: int, request: RejectSearchSessionRequest, session: Session = Depends(get_db_session)) -> SearchSessionRead:
    search_session = session.get(SearchSession, search_session_id)
    if search_session is None:
        raise HTTPException(status_code=404, detail="Search session not found")
    search_session.status = SearchStatus.rejected.value
    if search_session.run_id is not None:
        AgentRunRepository(session).append_event(
            search_session.run_id,
            "search_session_rejected",
            level=EventLevel.info.value,
            payload_json={"search_session_id": search_session.id, "reason": request.reason},
        )
    session.flush()
    return search_session_read(search_session)


@router.post("/agent/runs/{run_id}/approval", response_model=RunRead)
def approve_run(run_id: int, request: ApprovalRequest, session: Session = Depends(get_db_session)) -> RunRead:
    run = session.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    AgentRunRepository(session).append_event(run.id, "approval_decision", payload_json=request.model_dump())
    if request.decision == "cancel":
        run.status = RunStatus.cancelled.value
    elif request.decision == "reject" and run.status in {RunStatus.pending.value, RunStatus.running.value, RunStatus.waiting_for_user.value}:
        run.status = RunStatus.partial.value
    session.flush()
    return run_read(run)
