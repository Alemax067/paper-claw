from __future__ import annotations

import re
import tarfile
import tempfile
import zipfile
from pathlib import Path

from backend.db.types import ParseStrategy
from backend.integrations.parsers.cleaning import clean_extracted_text, clean_markdown_text
from backend.schemas import ParsedDocumentPayload

_SECTION_RE = re.compile(r"\\(?:section|subsection|subsubsection)\*?\{([^{}]+)\}")
_COMMAND_RE = re.compile(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{([^{}]*)\})?")
_INLINE_MATH_RE = re.compile(r"\$([^$]+)\$")
_COMMENT_RE = re.compile(r"(?<!\\)%.*")


class TexSourceParser:
    def parse(self, artifact_path: Path, warnings: list[str] | None = None) -> ParsedDocumentPayload:
        artifact_path = artifact_path.expanduser().resolve()
        tex_files = _extract_tex_files(artifact_path)
        if not tex_files:
            raise ValueError(f"No .tex files found in {artifact_path}.")
        main_tex = _select_main_tex(tex_files)
        tex_content = main_tex.read_text(encoding="utf-8", errors="ignore")
        markdown = _tex_to_markdown(tex_content)
        plain_text = clean_extracted_text(markdown)
        return ParsedDocumentPayload(
            strategy=ParseStrategy.tex.value,
            parser_kind="tex_source",
            plain_text=plain_text,
            markdown_content=markdown,
            json_content={"source_path": str(artifact_path), "main_tex": str(main_tex), "tex_files": [str(path) for path in tex_files]},
            quality_summary=f"Parsed TeX source from {main_tex.name}.",
            warnings=warnings or [],
        )


def _extract_tex_files(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(path.rglob("*.tex"))
    if path.suffix.lower() == ".tex":
        return [path]
    if zipfile.is_zipfile(path):
        temp_dir = Path(tempfile.mkdtemp(prefix="paper-claw-tex-"))
        with zipfile.ZipFile(path) as archive:
            archive.extractall(temp_dir)
        return sorted(temp_dir.rglob("*.tex"))
    if tarfile.is_tarfile(path):
        temp_dir = Path(tempfile.mkdtemp(prefix="paper-claw-tex-"))
        with tarfile.open(path) as archive:
            archive.extractall(temp_dir, filter="data")
        return sorted(temp_dir.rglob("*.tex"))
    return []


def _select_main_tex(tex_files: list[Path]) -> Path:
    for path in tex_files:
        name = path.name.lower()
        if name in {"main.tex", "paper.tex", "ms.tex"}:
            return path
    return max(tex_files, key=lambda path: path.stat().st_size)


def _tex_to_markdown(content: str) -> str:
    body_match = re.search(r"\\begin\{document\}(.*?)\\end\{document\}", content, flags=re.DOTALL)
    if body_match:
        content = body_match.group(1)
    content = _COMMENT_RE.sub("", content)
    content = _SECTION_RE.sub(lambda match: f"\n\n## {match.group(1).strip()}\n\n", content)
    content = _INLINE_MATH_RE.sub(lambda match: match.group(1), content)
    content = _COMMAND_RE.sub(lambda match: match.group(1) or "", content)
    content = content.replace("~", " ").replace("\\&", "&")
    return clean_markdown_text(content)
