from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool

from backend.services.acquisition import AcquisitionService
from backend.services.storage import ArtifactStorageService
from backend.tools.context import resolve_active_paper_id, tool_session


@tool
def acquire_paper_artifacts(paper_id: int | None = None, thread_id: int | None = None, run_id: int | None = None) -> dict:
    """Plan paper artifact acquisition using existing source/PDF artifacts or upload requirements."""
    with tool_session() as session:
        resolved_paper_id = resolve_active_paper_id(session, paper_id)
        job = AcquisitionService(session).plan_acquisition(resolved_paper_id, thread_id=thread_id, run_id=run_id)
        return {"acquisition_job_id": job.id, "status": job.status, "requested_source": job.requested_source, "input": job.input_json, "result": job.result_json}


@tool
def register_local_paper_pdf(path: str, paper_id: int | None = None) -> dict:
    """Register a local PDF file as a paper artifact."""
    with tool_session() as session:
        resolved_paper_id = resolve_active_paper_id(session, paper_id)
        artifact = ArtifactStorageService(session).register_local_pdf(resolved_paper_id, Path(path))
        return {"artifact_id": artifact.id, "kind": artifact.kind, "storage_uri": artifact.storage_uri}


@tool
def register_local_paper_source(path: str, paper_id: int | None = None) -> dict:
    """Register a local TeX source file/archive as a paper artifact."""
    with tool_session() as session:
        resolved_paper_id = resolve_active_paper_id(session, paper_id)
        artifact = ArtifactStorageService(session).register_source_artifact(resolved_paper_id, Path(path))
        return {"artifact_id": artifact.id, "kind": artifact.kind, "storage_uri": artifact.storage_uri}
