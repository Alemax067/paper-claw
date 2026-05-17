from __future__ import annotations

from backend.db.models import Paper
from backend.db.repositories import ParsingRepository
from backend.db.types import ProcessedDocumentStatus, SectionRole
from backend.services.document_processing import DocumentProcessingService, extract_references, split_markdown_sections


MARKDOWN = """# Sample Paper

<!-- page 1 -->

## Abstract

This paper studies retrieval augmented generation.

## Method

We use evidence chunks for grounded answers.

## References

[1] A. Author. A DOI paper. doi:10.1000/ABC123.
[2] B. Author. An arXiv paper. arXiv:2401.00001v2 https://example.com/paper
"""


def create_parsed_document(session, markdown: str = MARKDOWN):
    paper = Paper(title="Sample Paper")
    session.add(paper)
    session.flush()
    repo = ParsingRepository(session)
    job = repo.create_parse_job(paper.id, status="succeeded", strategy="tex")
    parsed = repo.create_parsed_document(
        paper.id,
        job.id,
        "tex_source",
        markdown_content=markdown,
        plain_text=markdown,
        quality_status="usable",
    )
    session.commit()
    return paper, parsed


def test_split_markdown_sections_classifies_roles():
    sections = split_markdown_sections(MARKDOWN)

    assert [section.heading_path[-1] for section in sections] == ["Sample Paper", "Abstract", "Method", "References"]
    assert [section.role for section in sections] == [SectionRole.title.value, SectionRole.abstract.value, SectionRole.body.value, SectionRole.reference.value]
    assert sections[1].page_start == 1


def test_extract_references():
    references = extract_references(split_markdown_sections(MARKDOWN))

    assert references[0]["doi"] == "10.1000/abc123"
    assert references[0]["title"] == "A DOI paper"
    assert references[0]["authors_json"] == ["A. Author"]
    assert references[1]["arxiv_id"] == "2401.00001"
    assert references[1]["url"] == "https://example.com/paper"


def test_process_parsed_document_creates_ready_document_sections_chunks_references(session):
    paper, parsed = create_parsed_document(session)

    processed = DocumentProcessingService(session, chunk_size_chars=80, chunk_overlap_chars=10).process_parsed_document(parsed.id)

    assert processed.status == ProcessedDocumentStatus.ready.value
    assert processed.content_markdown == MARKDOWN.strip()
    assert processed.metadata_json["analysis_excludes_roles"] == [SectionRole.reference.value]
    assert processed.metadata_json["skipped_chunk_roles"] == [SectionRole.reference.value]
    assert len(processed.sections) == 4
    assert len(processed.chunks) >= 3
    assert all(chunk.role != SectionRole.reference.value for chunk in processed.chunks)
    assert all("A DOI paper" not in chunk.content_text for chunk in processed.chunks)
    assert len(processed.references) == 2
    assert processed.references[0].doi == "10.1000/abc123"
    assert processed.references[0].authors_json == ["A. Author"]
    assert processed.references[0].title == "A DOI paper"


def test_chunk_key_and_index_are_unique(session):
    _, parsed = create_parsed_document(session, "# Body\n\n" + "abcdef " * 100)

    processed = DocumentProcessingService(session, chunk_size_chars=120, chunk_overlap_chars=20).process_parsed_document(parsed.id)

    chunk_keys = [chunk.chunk_key for chunk in processed.chunks]
    chunk_indexes = [chunk.chunk_index for chunk in processed.chunks]
    assert len(chunk_keys) == len(set(chunk_keys))
    assert chunk_indexes == list(range(1, len(chunk_indexes) + 1))


def test_process_latest_parsed_document(session):
    paper, _ = create_parsed_document(session)

    processed = DocumentProcessingService(session).process_latest_parsed_document(paper.id)

    assert processed.paper_id == paper.id
    assert processed.status == ProcessedDocumentStatus.ready.value


def test_repeated_processing_regenerates_deterministically(session):
    _, parsed = create_parsed_document(session)
    service = DocumentProcessingService(session, chunk_size_chars=100, chunk_overlap_chars=10)

    first = service.process_parsed_document(parsed.id)
    first_shape = ([section.cleaned_text for section in first.sections], [chunk.content_text for chunk in first.chunks])
    second = service.process_parsed_document(parsed.id)
    second_shape = ([section.cleaned_text for section in second.sections], [chunk.content_text for chunk in second.chunks])

    assert first.id != second.id
    assert second.version == 1
    assert first_shape == second_shape
