from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.db.models import AcquisitionJob, Artifact, Paper, PaperArtifact
from backend.db.repositories import ArtifactRepository
from backend.db.types import AcquisitionSource, ArtifactKind, ArtifactStatus, PaperArtifactRole, RunStatus
from backend.services.storage import ArtifactStorageService

Downloader = Callable[[str, Path], Path]


class AcquisitionService:
    def __init__(self, session: Session, storage_service: ArtifactStorageService | None = None) -> None:
        self.session = session
        self.storage_service = storage_service or ArtifactStorageService(session)

    def plan_acquisition(self, paper_id: int, *, thread_id: int | None = None, run_id: int | None = None) -> AcquisitionJob:
        paper = self._get_paper(paper_id)
        source_artifact = self._find_available_artifact(paper_id, PaperArtifactRole.source.value)
        pdf_artifact = self._find_available_artifact(paper_id, PaperArtifactRole.pdf.value)
        repo = ArtifactRepository(self.session)
        if source_artifact is not None:
            return repo.create_acquisition_job(
                paper_id,
                AcquisitionSource.manual_upload.value,
                thread_id=thread_id,
                run_id=run_id,
                status=RunStatus.succeeded.value,
                result_json={"artifact_id": source_artifact.id, "role": PaperArtifactRole.source.value, "next_step": "parse_tex_source"},
            )
        if pdf_artifact is not None:
            return repo.create_acquisition_job(
                paper_id,
                AcquisitionSource.manual_upload.value,
                thread_id=thread_id,
                run_id=run_id,
                status=RunStatus.succeeded.value,
                result_json={"artifact_id": pdf_artifact.id, "role": PaperArtifactRole.pdf.value, "next_step": "parse_pdf"},
            )
        if paper.best_pdf_url:
            return repo.create_acquisition_job(
                paper_id,
                _source_from_url(paper.best_pdf_url),
                thread_id=thread_id,
                run_id=run_id,
                status=RunStatus.pending.value,
                input_json={"pdf_url": paper.best_pdf_url},
                result_json={"next_step": "download_pdf"},
            )
        return repo.create_acquisition_job(
            paper_id,
            AcquisitionSource.manual_upload.value,
            thread_id=thread_id,
            run_id=run_id,
            status=RunStatus.waiting_for_user.value,
            input_json={"required": ["pdf", "source_archive"]},
            result_json={"message": "Upload a TeX source archive or PDF for this paper."},
        )

    def acquire_pdf_from_url(self, paper_id: int, pdf_url: str, downloader: Downloader) -> AcquisitionJob:
        paper = self._get_paper(paper_id)
        job = ArtifactRepository(self.session).create_acquisition_job(
            paper_id,
            _source_from_url(pdf_url),
            status=RunStatus.running.value,
            input_json={"pdf_url": pdf_url},
        )
        destination = self.storage_service.storage.paper_file_path(paper.id, "original.pdf")
        try:
            downloaded_path = downloader(pdf_url, destination)
            artifact = self.storage_service.register_local_pdf(paper.id, downloaded_path, original_filename="original.pdf")
            paper.best_pdf_url = paper.best_pdf_url or pdf_url
            job.status = RunStatus.succeeded.value
            job.result_json = {"artifact_id": artifact.id, "storage_uri": artifact.storage_uri}
        except Exception as exc:
            job.status = RunStatus.failed.value
            job.error_message = str(exc)
        self.session.flush()
        return job

    def _get_paper(self, paper_id: int) -> Paper:
        paper = self.session.get(Paper, paper_id)
        if paper is None:
            raise ValueError(f"Paper {paper_id} does not exist.")
        return paper

    def _find_available_artifact(self, paper_id: int, role: str) -> Artifact | None:
        return self.session.scalar(
            select(Artifact)
            .join(PaperArtifact)
            .options(selectinload(Artifact.paper_artifacts))
            .where(
                PaperArtifact.paper_id == paper_id,
                PaperArtifact.role == role,
                Artifact.status == ArtifactStatus.available.value,
            )
            .order_by(PaperArtifact.is_primary.desc(), Artifact.created_at.desc())
        )


def _source_from_url(url: str) -> str:
    if "arxiv.org" in url.lower():
        return AcquisitionSource.arxiv.value
    return AcquisitionSource.url.value
