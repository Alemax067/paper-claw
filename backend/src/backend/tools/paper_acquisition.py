from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool

from backend.services.acquisition import AcquisitionService
from backend.services.storage import ArtifactStorageService
from backend.tools.context import tool_session


@tool
def acquire_paper_artifacts(paper_id: int, thread_id: int | None = None, run_id: int | None = None) -> dict:
    """Plan paper artifact acquisition using existing source/PDF artifacts or upload requirements."""
    with tool_session() as session:
        job = AcquisitionService(session).plan_acquisition(paper_id, thread_id=thread_id, run_id=run_id)
        return {"acquisition_job_id": job.id, "status": job.status, "requested_source": job.requested_source, "input": job.input_json, "result": job.result_json}


@tool
def register_local_paper_pdf(paper_id: int, path: str) -> dict:
    """Register a local PDF file as a paper artifact."""
    with tool_session() as session:
        artifact = ArtifactStorageService(session).register_local_pdf(paper_id, Path(path))
        return {"artifact_id": artifact.id, "kind": artifact.kind, "storage_uri": artifact.storage_uri}


@tool
def register_local_paper_source(paper_id: int, path: str) -> dict:
    """Register a local TeX source file/archive as a paper artifact."""
    with tool_session() as session:
        artifact = ArtifactStorageService(session).register_source_artifact(paper_id, Path(path))
        return {"artifact_id": artifact.id, "kind": artifact.kind, "storage_uri": artifact.storage_uri}
