from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from backend.db.models import Paper, ParsedDocument, ParserEvent
from backend.db.types import ArtifactKind, ArtifactStatus, ParseJobStatus, ParseStrategy, PaperArtifactRole, StorageBackend
from backend.integrations.parsers import LlamaParseConfig, LlamaParseParser, LocalOCRConfig, LocalOCRParser, TexSourceParser
from backend.schemas import ParsedDocumentPayload
from backend.services.parsing import ParseChainService
from backend.services.storage import ArtifactStorageService
from backend.integrations.storage import LocalStorage


class FakeParser:
    def __init__(self, strategy: str, parser_kind: str = "fake", fail: bool = False) -> None:
        self.strategy = strategy
        self.parser_kind = parser_kind
        self.fail = fail
        self.received_warnings: list[str] | None = None

    def parse(self, artifact_path: Path, warnings: list[str] | None = None) -> ParsedDocumentPayload:
        self.received_warnings = warnings
        if self.fail:
            raise RuntimeError(f"{self.strategy} failed")
        return ParsedDocumentPayload(
            strategy=self.strategy,
            parser_kind=self.parser_kind,
            plain_text=f"{self.strategy} text",
            markdown_content=f"# {self.strategy}",
            json_content={"artifact_path": str(artifact_path)},
            warnings=warnings or [],
        )


def make_storage(session, tmp_path):
    root = tmp_path / "data" / "files"
    return root, ArtifactStorageService(session, LocalStorage(root))


def make_paper(session, title="Paper"):
    paper = Paper(title=title)
    session.add(paper)
    session.commit()
    return paper


def test_tex_source_parser_extracts_markdown(tmp_path):
    tex = tmp_path / "main.tex"
    tex.write_text(r"""
\documentclass{article}
\begin{document}
\title{A Paper}
\section{Abstract}
This is \textbf{important} text.
\end{document}
""", encoding="utf-8")

    payload = TexSourceParser().parse(tex)

    assert payload.strategy == ParseStrategy.tex.value
    assert "## Abstract" in payload.markdown_content
    assert "important" in payload.plain_text


def test_plan_parse_chain_prefers_tex_source_over_pdf(session, tmp_path):
    paper = make_paper(session)
    root, storage = make_storage(session, tmp_path)
    source = tmp_path / "source.tex"
    source.write_text("\\begin{document}TeX\\end{document}")
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"pdf")
    storage.register_source_artifact(paper.id, source)
    storage.register_local_pdf(paper.id, pdf)

    plan = ParseChainService(
        session,
        {ParseStrategy.tex.value: FakeParser(ParseStrategy.tex.value), ParseStrategy.local_ocr.value: FakeParser(ParseStrategy.local_ocr.value)},
        root,
    ).plan_parse_chain(paper.id)

    assert plan.selected_strategy == ParseStrategy.tex.value


def test_run_parse_chain_persists_events_and_document(session, tmp_path):
    paper = make_paper(session)
    root, storage = make_storage(session, tmp_path)
    source = tmp_path / "source.tex"
    source.write_text("\\begin{document}TeX\\end{document}")
    storage.register_source_artifact(paper.id, source)

    job = ParseChainService(session, {ParseStrategy.tex.value: FakeParser(ParseStrategy.tex.value, "tex_fake")}, root).run_parse_chain(paper.id)

    assert job.status == ParseJobStatus.succeeded.value
    assert job.strategy == ParseStrategy.tex.value
    document = session.query(ParsedDocument).one()
    assert document.parser_kind == "tex_fake"
    assert [event.sequence for event in session.query(ParserEvent).order_by(ParserEvent.sequence)] == [1, 2, 3]


def test_local_ocr_selected_when_only_pdf_and_parser_exists(session, tmp_path):
    paper = make_paper(session)
    root, storage = make_storage(session, tmp_path)
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"pdf")
    storage.register_local_pdf(paper.id, pdf)

    plan = ParseChainService(session, {ParseStrategy.local_ocr.value: FakeParser(ParseStrategy.local_ocr.value)}, root).plan_parse_chain(paper.id)

    assert plan.selected_strategy == ParseStrategy.local_ocr.value


def test_llama_parse_selected_when_local_ocr_missing(session, tmp_path):
    paper = make_paper(session)
    root, storage = make_storage(session, tmp_path)
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"pdf")
    storage.register_local_pdf(paper.id, pdf)

    plan = ParseChainService(session, {ParseStrategy.llama_parse.value: FakeParser(ParseStrategy.llama_parse.value)}, root).plan_parse_chain(paper.id)

    assert plan.selected_strategy == ParseStrategy.llama_parse.value


def test_unavailable_when_no_parseable_artifact_or_backend(session):
    paper = make_paper(session)

    job = ParseChainService(session).run_parse_chain(paper.id)

    assert job.status == ParseJobStatus.failed.value
    assert job.strategy == ParseStrategy.unavailable.value
    assert "No parseable" in job.error_message


def test_failed_earlier_strategy_warning_reaches_later_success(session, tmp_path):
    paper = make_paper(session)
    root, storage = make_storage(session, tmp_path)
    source = tmp_path / "source.tex"
    source.write_text("\\begin{document}TeX\\end{document}")
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"pdf")
    storage.register_source_artifact(paper.id, source)
    storage.register_local_pdf(paper.id, pdf)
    local_ocr = FakeParser(ParseStrategy.local_ocr.value, "ocr_fake")

    job = ParseChainService(
        session,
        {ParseStrategy.tex.value: FakeParser(ParseStrategy.tex.value, fail=True), ParseStrategy.local_ocr.value: local_ocr},
        root,
    ).run_parse_chain(paper.id)

    assert job.status == ParseJobStatus.succeeded.value
    assert local_ocr.received_warnings == ["tex: tex failed"]
    assert session.query(ParsedDocument).one().json_content["warnings"] == ["tex: tex failed"]


def test_local_ocr_parser_uses_openai_compatible_multimodal_client(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"pdf")
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="<h1>Title</h1><p>Body</p>"))],
        usage={"total_tokens": 3},
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: response)))
    pixmap = SimpleNamespace(tobytes=lambda format: b"png")
    page = SimpleNamespace(get_pixmap=lambda dpi: pixmap)

    class FakeDocument:
        page_count = 1

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def load_page(self, index):
            return page

    fitz = SimpleNamespace(open=lambda path: FakeDocument())

    payload = LocalOCRParser(LocalOCRConfig(base_url="http://local", model="ocr"), client=client, fitz_module=fitz).parse(pdf)

    assert payload.strategy == ParseStrategy.local_ocr.value
    assert payload.json_content["page_count"] == 1
    assert "Title" in payload.markdown_content


def test_llama_parse_parser_uses_injected_parser(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"pdf")
    parser = SimpleNamespace(load_data=lambda path: [SimpleNamespace(text="# Parsed")])

    payload = LlamaParseParser(LlamaParseConfig(api_key="test"), parser=parser).parse(pdf)

    assert payload.strategy == ParseStrategy.llama_parse.value
    assert payload.markdown_content == "# Parsed"
