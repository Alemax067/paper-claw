from __future__ import annotations

from pathlib import Path

import pytest

from backend.db.models import Artifact, Paper, PaperArtifact
from backend.db.types import ArtifactKind, PaperArtifactRole, RunStatus
from backend.integrations.storage import LocalStorage
from backend.services.acquisition import AcquisitionService
from backend.services.storage import ArtifactStorageService


def make_storage_service(session, tmp_path: Path) -> ArtifactStorageService:
    return ArtifactStorageService(session, LocalStorage(tmp_path / "data" / "files"))


def test_register_local_pdf(session, tmp_path):
    paper = Paper(title="PDF paper")
    session.add(paper)
    session.commit()
    pdf = tmp_path / "input.pdf"
    pdf.write_bytes(b"pdf")

    artifact = make_storage_service(session, tmp_path).register_local_pdf(paper.id, pdf)

    assert artifact.kind == ArtifactKind.pdf.value
    assert artifact.storage_uri == f"local://papers/{paper.id}/original.pdf"
    assert artifact.size_bytes == 3
    link = session.query(PaperArtifact).one()
    assert link.role == PaperArtifactRole.pdf.value
    assert link.is_primary is True


def test_register_source_artifact(session, tmp_path):
    paper = Paper(title="Source paper")
    session.add(paper)
    session.commit()
    source = tmp_path / "source.zip"
    source.write_bytes(b"source")

    artifact = make_storage_service(session, tmp_path).register_source_artifact(paper.id, source)

    assert artifact.kind == ArtifactKind.source_archive.value
    assert artifact.storage_uri == f"local://papers/{paper.id}/source/source.zip"
    assert session.query(PaperArtifact).one().role == PaperArtifactRole.source.value


def test_link_paper_artifact_is_idempotent(session, tmp_path):
    paper = Paper(title="Linked paper")
    artifact = Artifact(kind=ArtifactKind.pdf.value, storage_uri="local://papers/1/original.pdf")
    session.add_all([paper, artifact])
    session.commit()
    service = make_storage_service(session, tmp_path)

    first = service.link_paper_artifact(paper.id, artifact.id, PaperArtifactRole.pdf.value)
    second = service.link_paper_artifact(paper.id, artifact.id, PaperArtifactRole.pdf.value, is_primary=True)

    assert first.id == second.id
    assert second.is_primary is True
    assert session.query(PaperArtifact).count() == 1


def test_local_storage_rejects_paths_outside_root(tmp_path):
    storage = LocalStorage(tmp_path / "root")
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"x")

    with pytest.raises(ValueError, match="under the configured root"):
        storage.describe_file(outside)


def test_acquisition_prefers_source_artifact(session, tmp_path):
    paper = Paper(title="Source first")
    session.add(paper)
    session.commit()
    source = tmp_path / "source.zip"
    source.write_bytes(b"source")
    storage_service = make_storage_service(session, tmp_path)
    artifact = storage_service.register_source_artifact(paper.id, source)

    job = AcquisitionService(session, storage_service).plan_acquisition(paper.id)

    assert job.status == RunStatus.succeeded.value
    assert job.result_json["artifact_id"] == artifact.id
    assert job.result_json["next_step"] == "parse_tex_source"


def test_acquisition_uses_existing_pdf(session, tmp_path):
    paper = Paper(title="PDF exists")
    session.add(paper)
    session.commit()
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"pdf")
    storage_service = make_storage_service(session, tmp_path)
    artifact = storage_service.register_local_pdf(paper.id, pdf)

    job = AcquisitionService(session, storage_service).plan_acquisition(paper.id)

    assert job.status == RunStatus.succeeded.value
    assert job.result_json["artifact_id"] == artifact.id
    assert job.result_json["next_step"] == "parse_pdf"


def test_acquisition_returns_pending_when_pdf_url_exists(session, tmp_path):
    paper = Paper(title="Downloadable", best_pdf_url="https://arxiv.org/pdf/2401.00001")
    session.add(paper)
    session.commit()

    job = AcquisitionService(session, make_storage_service(session, tmp_path)).plan_acquisition(paper.id)

    assert job.status == RunStatus.pending.value
    assert job.requested_source == "arxiv"
    assert job.input_json == {"pdf_url": "https://arxiv.org/pdf/2401.00001"}


def test_acquisition_returns_upload_needed_when_no_artifact_or_url(session, tmp_path):
    paper = Paper(title="Needs upload")
    session.add(paper)
    session.commit()

    job = AcquisitionService(session, make_storage_service(session, tmp_path)).plan_acquisition(paper.id)

    assert job.status == RunStatus.waiting_for_user.value
    assert job.input_json == {"required": ["pdf", "source_archive"]}


def test_acquire_pdf_from_url_uses_downloader_and_registers_pdf(session, tmp_path):
    paper = Paper(title="Download paper")
    session.add(paper)
    session.commit()
    storage_service = make_storage_service(session, tmp_path)

    def downloader(url: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(url.encode())
        return destination

    job = AcquisitionService(session, storage_service).acquire_pdf_from_url(paper.id, "https://example.com/paper.pdf", downloader)

    assert job.status == RunStatus.succeeded.value
    assert job.result_json["storage_uri"] == f"local://papers/{paper.id}/original.pdf"
    assert session.query(PaperArtifact).one().role == PaperArtifactRole.pdf.value
