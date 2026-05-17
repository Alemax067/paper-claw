from __future__ import annotations

import re
import tarfile
import tempfile
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from backend.db.types import ParseStrategy
from backend.integrations.parsers.cleaning import clean_extracted_text, clean_markdown_text
from backend.schemas import ParsedDocumentPayload

_HEADING_COMMANDS: tuple[tuple[str, str], ...] = (
    ("section", "##"),
    ("subsection", "###"),
    ("subsubsection", "####"),
    ("paragraph", "#####"),
)
_INLINE_COMMANDS = "textbf|textit|emph|underline|texttt|textrm|mathrm|mathbf|mathit|operatorname|textsc"
_DOCUMENT_ENV_RE = re.compile(r"\\begin\{document\}(.*?)\\end\{document\}", re.IGNORECASE | re.DOTALL)
_ABSTRACT_ENV_RE = re.compile(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", re.IGNORECASE | re.DOTALL)
_TITLE_COMMAND_RE = re.compile(r"\\(?:title|icmltitle)\*?(?:\[[^\]]*\])?\s*\{", re.IGNORECASE)
_INCLUDE_RE = re.compile(r"\\(?:input|include)\s*(?:\[[^\]]*\])?\{([^}]+)\}", re.IGNORECASE)
_BIB_RESOURCE_RE = re.compile(r"\\(?:bibliography|addbibresource)\s*\{([^}]*)\}", re.IGNORECASE)
_THEBIB_ENV_RE = re.compile(r"\\begin\{thebibliography\}(?:\{[^}]*\})?(.*?)\\end\{thebibliography\}", re.IGNORECASE | re.DOTALL)
_FLOAT_ENV_RE = re.compile(r"\\begin\{(figure\*?|table\*?)\}(?:\[[^\]]*\])?(.*?)\\end\{\1\}", re.IGNORECASE | re.DOTALL)
_MATH_ENV_RE = re.compile(r"\\begin\{(equation\*?|align\*?|gather\*?|multline\*?)\}(.*?)\\end\{\1\}", re.IGNORECASE | re.DOTALL)
_DISPLAY_MATH_RE = re.compile(r"\\\[(.*?)\\\]", re.DOTALL)
_INLINE_MATH_RE = re.compile(r"\\\((.*?)\\\)|(?<!\$)\$(?!\$)([^$\n]+?)(?<!\$)\$(?!\$)")
_SIMPLE_MACRO_RE = re.compile(
    r"(?:\\def\\(?P<def_name>[A-Za-z@]+)(?!\s*#)\s*\{(?P<def_value>(?:[^{}]|\{[^{}]*\})*)\}|"
    r"\\newcommand\s*\{\\(?P<new_name>[A-Za-z@]+)\}\s*(?:\[0\])?\s*\{(?P<new_value>(?:[^{}]|\{[^{}]*\})*)\})",
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class _ParseState:
    warnings: list[str] = field(default_factory=list)
    used_files: list[str] = field(default_factory=list)
    missing_includes: list[str] = field(default_factory=list)
    simple_macros: dict[str, str] = field(default_factory=dict)


class TexSourceParser:
    def parse(self, artifact_path: Path, warnings: list[str] | None = None) -> ParsedDocumentPayload:
        artifact_path = artifact_path.expanduser().resolve()
        state = _ParseState(warnings=list(warnings or []))
        with _prepare_source_root(artifact_path, state) as source_root:
            tex_files = sorted(path for path in source_root.rglob("*.tex") if path.is_file())
            if not tex_files:
                raise ValueError(f"No .tex files found in {artifact_path}.")
            main_tex = _select_main_tex(tex_files, source_root)
            expanded = _expand_tex_file(main_tex, source_root, state=state, seen=set(), depth=0)
            title = _extract_title(expanded) or _cleanup_inline_tex(main_tex.stem.replace("_", " "))
            abstract = _extract_abstract(expanded)
            references = _extract_reference_entries(expanded, source_root, state)
            markdown = _build_markdown_document(expanded, title=title, abstract=abstract, references=references, state=state)
            markdown = clean_markdown_text(markdown)
            plain_text = clean_extracted_text(_markdown_to_plain(markdown))
            bib_files = sorted(path for path in source_root.rglob("*.bib") if path.is_file())
            return ParsedDocumentPayload(
                strategy=ParseStrategy.tex.value,
                parser_kind="tex_source",
                plain_text=plain_text,
                markdown_content=markdown,
                json_content={
                    "source_path": str(artifact_path),
                    "source_root": str(source_root),
                    "main_tex": _relative_path(main_tex, source_root),
                    "tex_files": [_relative_path(path, source_root) for path in tex_files],
                    "bib_files": [_relative_path(path, source_root) for path in bib_files],
                    "used_files": state.used_files,
                    "missing_includes": state.missing_includes,
                    "references_count": len(references),
                },
                quality_summary=f"Parsed TeX source from {_relative_path(main_tex, source_root)} with {len(state.used_files)} source files and {len(references)} references.",
                warnings=state.warnings,
            )


@contextmanager
def _prepare_source_root(path: Path, state: _ParseState) -> Iterator[Path]:
    if path.is_dir():
        yield path
        return
    if path.suffix.lower() == ".tex":
        yield path.parent
        return
    with tempfile.TemporaryDirectory(prefix="paper-claw-tex-") as temp_dir:
        root = Path(temp_dir) / "source"
        root.mkdir(parents=True, exist_ok=True)
        if zipfile.is_zipfile(path):
            _safe_extract_zip(path, root, state)
            yield root
            return
        if tarfile.is_tarfile(path):
            with tarfile.open(path) as archive:
                _safe_extract_tar(archive, root, state)
            yield root
            return
        raise ValueError(f"Unsupported TeX source artifact: {path}")


def _safe_extract_zip(path: Path, destination: Path, state: _ParseState) -> None:
    destination = destination.resolve()
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            target = (destination / info.filename.lstrip("/")).resolve()
            try:
                target.relative_to(destination)
            except ValueError:
                state.warnings.append(f"Skipped unsafe archive member: {info.filename}")
                continue
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(info))


def _safe_extract_tar(archive: tarfile.TarFile, destination: Path, state: _ParseState) -> None:
    destination = destination.resolve()
    members = []
    for member in archive.getmembers():
        target = (destination / member.name.lstrip("/")).resolve()
        try:
            target.relative_to(destination)
        except ValueError:
            state.warnings.append(f"Skipped unsafe archive member: {member.name}")
            continue
        if member.issym() or member.islnk():
            state.warnings.append(f"Skipped linked archive member: {member.name}")
            continue
        members.append(member)
    archive.extractall(destination, members=members, filter="data")


def _select_main_tex(tex_files: list[Path], source_root: Path) -> Path:
    def score(path: Path) -> tuple[int, int, int]:
        text = _read_text_file(path)
        name = path.name.lower()
        lowered_path = _relative_path(path, source_root).lower()
        value = 0
        if "\\documentclass" in text:
            value += 10
        if "\\begin{document}" in text:
            value += 10
        if name in {"main.tex", "paper.tex", "ms.tex", "article.tex"}:
            value += 5
        if name.startswith("main"):
            value += 2
        if any(part in lowered_path for part in ("supplement", "appendix", "response", "rebuttal", "template")):
            value -= 5
        value += min(len(re.findall(r"\\(?:section|subsection|subsubsection)\*?\{", text)), 8)
        return value, -len(path.parts), -path.stat().st_size

    return max(tex_files, key=score)


def _expand_tex_file(path: Path, source_root: Path, *, state: _ParseState, seen: set[Path], depth: int) -> str:
    resolved = path.resolve()
    if resolved in seen:
        state.warnings.append(f"Skipped recursive include: {_relative_path(resolved, source_root)}")
        return ""
    if depth > 40:
        state.warnings.append(f"Maximum include depth exceeded at {_relative_path(resolved, source_root)}")
        return ""
    seen.add(resolved)
    relative = _relative_path(resolved, source_root)
    if relative not in state.used_files:
        state.used_files.append(relative)
    text = _strip_comments(_read_text_file(resolved)).split("\\endinput", 1)[0]
    _collect_simple_macros(text, state)

    def replace_include(match: re.Match[str]) -> str:
        raw = match.group(1).strip()
        include_path = _resolve_include_path(resolved.parent, raw, source_root)
        if include_path is None:
            state.missing_includes.append(raw)
            state.warnings.append(f"Missing include file: {raw}")
            return "\n\n"
        return "\n\n" + _expand_tex_file(include_path, source_root, state=state, seen=seen, depth=depth + 1) + "\n\n"

    return _INCLUDE_RE.sub(replace_include, text)


def _resolve_include_path(base_dir: Path, raw: str, source_root: Path) -> Path | None:
    value = raw.strip().strip('"').strip("'")
    if not value:
        return None
    candidate = Path(value)
    possibilities = [candidate] if candidate.suffix else [candidate.with_suffix(".tex"), candidate]
    roots = [base_dir.resolve(), source_root.resolve()]
    seen: set[Path] = set()
    for possibility in possibilities:
        for root in roots:
            resolved = (root / possibility).resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            if resolved.is_file() and _is_relative_to(resolved, source_root.resolve()):
                return resolved
        for matched in source_root.resolve().rglob(possibility.name):
            resolved = matched.resolve()
            if resolved not in seen and resolved.is_file() and _is_relative_to(resolved, source_root.resolve()):
                return resolved
    return None


def _extract_title(text: str) -> str | None:
    match = _TITLE_COMMAND_RE.search(text)
    if match is None:
        return None
    brace_index = text.find("{", match.start())
    value, _ = _read_braced_value(text, brace_index)
    cleaned = _cleanup_inline_tex(value)
    return cleaned or None


def _extract_abstract(text: str) -> str | None:
    match = _ABSTRACT_ENV_RE.search(text)
    return _cleanup_inline_tex(match.group(1)) if match else None


def _extract_reference_entries(text: str, source_root: Path, state: _ParseState) -> list[str]:
    entries: list[str] = []
    for match in _THEBIB_ENV_RE.finditer(text):
        entries.extend(_parse_thebibliography_entries(match.group(1)))
    if entries:
        return entries
    resource_names = _collect_bibliography_resource_names(text)
    bib_files = _resolve_bibliography_files(source_root, resource_names)
    if not bib_files and (resource_names or "\\printbibliography" in text):
        state.warnings.append("Bibliography resources were referenced but no .bib files were found")
    for bib_file in bib_files:
        entries.extend(_parse_bib_file(bib_file))
    return entries


def _collect_bibliography_resource_names(text: str) -> list[str]:
    names: list[str] = []
    for match in _BIB_RESOURCE_RE.finditer(text):
        for part in match.group(1).split(","):
            value = part.strip().strip('"').strip("'")
            if value:
                names.append(value)
    return names


def _resolve_bibliography_files(source_root: Path, names: list[str]) -> list[Path]:
    if not names:
        return sorted(path for path in source_root.rglob("*.bib") if path.is_file())
    resolved: list[Path] = []
    seen: set[Path] = set()
    for name in names:
        raw = Path(name)
        candidates = [raw] if raw.suffix else [raw.with_suffix(".bib"), raw]
        for candidate in candidates:
            direct = (source_root / candidate).resolve()
            if direct.is_file() and direct not in seen and _is_relative_to(direct, source_root.resolve()):
                resolved.append(direct)
                seen.add(direct)
                continue
            for matched in source_root.rglob(candidate.name):
                matched = matched.resolve()
                if matched.is_file() and matched not in seen and _is_relative_to(matched, source_root.resolve()):
                    resolved.append(matched)
                    seen.add(matched)
    return resolved


def _parse_thebibliography_entries(content: str) -> list[str]:
    parts = re.split(r"\\bibitem(?:\[[^\]]*\])?\{[^}]+\}", content)
    return [cleaned for part in parts[1:] if (cleaned := _cleanup_inline_tex(part))]


def _parse_bib_file(path: Path) -> list[str]:
    text = _read_text_file(path)
    starts = list(re.finditer(r"@\w+\s*\{", text))
    entries: list[str] = []
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        rendered = _render_bib_entry(text[match.start():end])
        if rendered:
            entries.append(rendered)
    return entries


def _render_bib_entry(block: str) -> str | None:
    title = _cleanup_inline_tex(_extract_bib_field(block, "title") or "")
    authors_raw = _extract_bib_field(block, "author") or ""
    year = _cleanup_inline_tex(_extract_bib_field(block, "year") or "")
    venue = _cleanup_inline_tex(_extract_bib_field(block, "journal") or _extract_bib_field(block, "booktitle") or "")
    doi = _cleanup_inline_tex(_extract_bib_field(block, "doi") or "")
    arxiv_id = _cleanup_inline_tex(_extract_bib_field(block, "eprint") or "")
    url = _cleanup_inline_tex(_extract_bib_field(block, "url") or "")
    authors = [_cleanup_inline_tex(author) for author in re.split(r"\band\b", authors_raw) if author.strip()]
    parts = [", ".join(authors), title, venue, year, f"DOI: {doi}" if doi else "", f"arXiv: {arxiv_id}" if arxiv_id else "", url]
    rendered = ". ".join(part.strip(" .") for part in parts if part and part.strip(" ."))
    return f"{rendered}." if rendered else None


def _extract_bib_field(block: str, field: str) -> str | None:
    match = re.search(rf"\b{re.escape(field)}\s*=\s*", block, re.IGNORECASE)
    if match is None:
        return None
    cursor = match.end()
    while cursor < len(block) and block[cursor].isspace():
        cursor += 1
    if cursor >= len(block):
        return None
    if block[cursor] == "{":
        value, _ = _read_braced_value(block, cursor)
        return value
    if block[cursor] == '"':
        end = cursor + 1
        while end < len(block):
            if block[end] == '"' and block[end - 1] != "\\":
                return block[cursor + 1:end]
            end += 1
        return block[cursor + 1:]
    end = block.find(",", cursor)
    return block[cursor:end if end >= 0 else len(block)].strip()


def _build_markdown_document(text: str, *, title: str | None, abstract: str | None, references: list[str], state: _ParseState) -> str:
    body = _extract_document_body(text)
    body = _expand_simple_macros(body, state)
    body = body.replace("\\maketitle", "\n\n")
    body = _ABSTRACT_ENV_RE.sub("\n\n", body)
    body = _THEBIB_ENV_RE.sub("\n\n", body)
    body = _BIB_RESOURCE_RE.sub("\n\n", body)
    body = re.sub(r"\\printbibliography\b", "\n\n", body)
    body = re.sub(r"\\appendix\b", "\n\n## Appendix\n\n", body, count=1)
    body = _FLOAT_ENV_RE.sub(lambda match: _render_float_block(match.group(1), match.group(2)), body)
    body = _unwrap_passthrough_environments(body)
    body = _drop_latex_environment_options(body)
    body = _MATH_ENV_RE.sub(lambda match: _render_display_math(match.group(2)), body)
    body = _DISPLAY_MATH_RE.sub(lambda match: _render_display_math(match.group(1)), body)
    body = _replace_heading_commands(body)
    body = re.sub(r"\\item\b", "\n- ", body)
    body = re.sub(r"\\begin\{(?:itemize|enumerate|description)\}|\\end\{(?:itemize|enumerate|description)\}", "\n\n", body)
    body = _cleanup_structured_tex_body(body)
    parts: list[str] = []
    if title:
        parts.append(f"# {title}")
    if abstract:
        parts.append(f"## Abstract\n\n{abstract}")
    if body.strip():
        parts.append(body.strip())
    if references:
        parts.append("## References\n\n" + "\n".join(f"- {entry}" for entry in references))
    return "\n\n".join(parts)


def _extract_document_body(text: str) -> str:
    match = _DOCUMENT_ENV_RE.search(text)
    return match.group(1) if match else text


def _render_float_block(env_name: str, content: str) -> str:
    label = "Figure" if env_name.lower().startswith("figure") else "Table"
    caption = _extract_command_argument(content, "caption")
    content = _remove_latex_command_arguments(content, "caption", 1)
    content = re.sub(r"\\includegraphics(?:\[[^\]]*\])?\{[^}]*\}", " ", content, flags=re.IGNORECASE)
    content = re.sub(r"\\label\{[^}]*\}", " ", content, flags=re.IGNORECASE)
    body = _cleanup_structured_tex_body(content)
    pieces = [f"{label}: {_cleanup_inline_tex(caption)}" if caption else ""]
    if body and body.casefold() not in {piece.casefold() for piece in pieces if piece}:
        pieces.append(body)
    return "\n\n" + "\n\n".join(piece for piece in pieces if piece.strip()) + "\n\n"


def _unwrap_passthrough_environments(text: str) -> str:
    environments = "center|tcolorbox|remark|theorem|lemma|proposition|corollary|definition|assumption|wrapfigure"
    text = re.sub(rf"\\begin\{{(?:{environments})\}}(?:\[[^\]]*\])?", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(rf"\\end\{{(?:{environments})\}}", "\n\n", text, flags=re.IGNORECASE)
    return text


def _drop_latex_environment_options(text: str) -> str:
    lines = text.splitlines()
    cleaned: list[str] = []
    skipping = False
    for line in lines:
        stripped = line.strip()
        if stripped == "[" or (stripped.startswith("[") and any(token in stripped for token in ("colback", "colframe", "boxrule", "enhanced"))):
            skipping = True
            if stripped.endswith("]"):
                skipping = False
            continue
        if skipping:
            if stripped.endswith("]"):
                skipping = False
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def _replace_heading_commands(text: str) -> str:
    result = text
    for command, prefix in _HEADING_COMMANDS:
        pattern = re.compile(rf"\\{command}\*?(?:\[[^\]]*\])?\{{((?:[^{{}}]|\{{[^{{}}]*\}})*)\}}", re.IGNORECASE)
        result = pattern.sub(lambda match: f"\n\n{prefix} {_cleanup_inline_tex(match.group(1)).strip()}\n\n", result)
    return result


def _cleanup_structured_tex_body(text: str) -> str:
    protected, replacements = _protect_inline_math(text)
    blocks = [block.strip() for block in re.split(r"\n\s*\n+", protected) if block.strip()]
    cleaned = []
    for block in blocks:
        if block.startswith("#") or block.startswith(("Figure:", "Table:")):
            cleaned.append(_restore_inline_math(block, replacements))
        else:
            value = _cleanup_inline_tex(block)
            if value and not _is_layout_artifact(value):
                cleaned.append(_restore_inline_math(value, replacements))
    return re.sub(r"\n{3,}", "\n\n", "\n\n".join(cleaned)).strip()


def _is_layout_artifact(text: str) -> bool:
    value = text.strip()
    return bool(re.fullmatch(r"-?\d+", value)) or value.casefold() in {"table of contents", "appendix"}


def _cleanup_inline_tex(text: str) -> str:
    protected, replacements = _protect_inline_math(text)
    protected = protected.replace("\r", " ").replace("\n", " ").replace("~", " ")
    protected = re.sub(r"\\(?:v|h)space\*?\s*\{[^{}]*\}", " ", protected)
    protected = re.sub(r"\\\\\s*(?:\[[^\]]*\])?", "\n", protected)
    protected = _remove_latex_command_arguments(protected, "fontsize", 2)
    protected = _unwrap_latex_command_argument(protected, "selectfont", 0)
    protected = _unwrap_latex_command_argument(protected, "raisebox", 2)
    protected = _remove_latex_command_arguments(protected, "includegraphics", 1)
    protected = protected.replace(r"\&", "&").replace(r"\%", "%").replace(r"\_", "_")
    protected = re.sub(r"\\href\s*\{([^}]*)\}\s*\{([^}]*)\}", r"\2 (\1)", protected)
    protected = re.sub(r"\\url\s*\{([^}]*)\}", r"\1", protected)
    protected = re.sub(r"\\(?:cite\w*|ref|eqref|autoref|pageref)\s*(?:\[[^\]]*\])?\{([^}]*)\}", r"[\1]", protected)
    protected = re.sub(r"\\label\s*\{[^}]*\}", " ", protected)
    protected = re.sub(r"\\footnote\s*\{([^}]*)\}", r" (\1)", protected)
    for _ in range(6):
        previous = protected
        protected = re.sub(rf"\\(?:{_INLINE_COMMANDS})\*?\s*\{{([^{{}}]*)\}}", lambda match: match.group(1), protected)
        if protected == previous:
            break
    protected = re.sub(r"\\[a-zA-Z@]+\*?(?:\[[^\]]*\])?(?:\{[^{}]*\})?", " ", protected)
    protected = protected.replace("{", " ").replace("}", " ").replace("$", " ")
    protected = re.sub(r"\\\\", "\n", protected)
    protected = re.sub(r"\s+", " ", protected).strip()
    protected = re.sub(r"\s+([.,;:!?])", r"\1", protected)
    return _restore_inline_math(protected, replacements)


def _protect_inline_math(text: str) -> tuple[str, dict[str, str]]:
    replacements: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        token = f"PAPERCLAWMATH{len(replacements)}"
        content = match.group(1) or match.group(2) or ""
        replacements[token] = f"${content.strip()}$"
        return token

    return _INLINE_MATH_RE.sub(replace, text), replacements


def _restore_inline_math(text: str, replacements: dict[str, str]) -> str:
    for token in sorted(replacements, key=len, reverse=True):
        text = text.replace(token, replacements[token])
    return text


def _render_display_math(content: str) -> str:
    return f"\n\n$$\n{content.strip()}\n$$\n\n" if content.strip() else "\n\n"


def _collect_simple_macros(text: str, state: _ParseState) -> None:
    for match in _SIMPLE_MACRO_RE.finditer(text):
        name = match.group("def_name") or match.group("new_name")
        value = match.group("def_value") or match.group("new_value") or ""
        if name and value.strip() and re.search(rf"\\(?:def|newcommand)\\{re.escape(name)}\s*#", match.group(0)) is None:
            state.simple_macros[name.strip()] = value.strip()


def _expand_simple_macros(text: str, state: _ParseState) -> str:
    expanded = text
    for _ in range(4):
        previous = expanded
        for name, value in sorted(state.simple_macros.items(), key=lambda item: len(item[0]), reverse=True):
            expanded = re.sub(rf"\\{re.escape(name)}\b", lambda _match, replacement=value: replacement, expanded)
        expanded = expanded.replace(r"\xspace", " ")
        if expanded == previous:
            break
    return expanded


def _extract_command_argument(text: str, command: str) -> str | None:
    match = re.search(rf"\\{re.escape(command)}\*?(?:\[[^\]]*\])?\s*\{{", text, re.IGNORECASE)
    if match is None:
        return None
    value, _ = _read_braced_value(text, text.find("{", match.start()))
    return value.strip() or None


def _remove_latex_command_arguments(text: str, command: str, required_args: int) -> str:
    return _rewrite_latex_command(text, command, required_args, lambda _args: " ")


def _unwrap_latex_command_argument(text: str, command: str, required_args: int) -> str:
    return _rewrite_latex_command(text, command, required_args, lambda args: args[-1] if args else " ")


def _rewrite_latex_command(text: str, command: str, required_args: int, render) -> str:
    pattern = re.compile(rf"\\{re.escape(command)}\*?(?:\[[^\]]*\])?", re.IGNORECASE)
    pieces: list[str] = []
    cursor = 0
    while True:
        match = pattern.search(text, cursor)
        if match is None:
            pieces.append(text[cursor:])
            break
        args: list[str] = []
        end = match.end()
        for _ in range(required_args):
            while end < len(text) and text[end].isspace():
                end += 1
            if end >= len(text) or text[end] != "{":
                break
            value, end = _read_braced_value(text, end)
            args.append(value)
        if len(args) != required_args:
            pieces.append(text[cursor:match.end()])
            cursor = match.end()
            continue
        pieces.append(text[cursor:match.start()])
        pieces.append(str(render(args)))
        cursor = end
    return "".join(pieces)


def _read_braced_value(text: str, opening_brace: int) -> tuple[str, int]:
    depth = 0
    collected: list[str] = []
    cursor = opening_brace
    while cursor < len(text):
        char = text[cursor]
        if char == "{":
            depth += 1
            if depth > 1:
                collected.append(char)
        elif char == "}":
            depth -= 1
            if depth == 0:
                return "".join(collected), cursor + 1
            if depth > 0:
                collected.append(char)
        elif depth > 0:
            collected.append(char)
        cursor += 1
    return "".join(collected), cursor


def _read_text_file(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _strip_comments(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        cursor = 0
        while True:
            index = line.find("%", cursor)
            if index < 0:
                lines.append(line)
                break
            backslashes = 0
            probe = index - 1
            while probe >= 0 and line[probe] == "\\":
                backslashes += 1
                probe -= 1
            if backslashes % 2 == 0:
                lines.append(line[:index])
                break
            cursor = index + 1
    return "\n".join(lines)


def _markdown_to_plain(markdown: str) -> str:
    text = re.sub(r"^\s*#+\s*", "", markdown, flags=re.MULTILINE)
    text = re.sub(r"^\s*-\s*", "", text, flags=re.MULTILINE)
    return text.strip()


def _relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False
