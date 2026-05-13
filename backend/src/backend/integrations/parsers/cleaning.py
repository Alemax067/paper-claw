from __future__ import annotations

import re

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def clean_markdown_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _SPACE_RE.sub(" ", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


def clean_extracted_text(text: str) -> str:
    text = _HTML_TAG_RE.sub(" ", text)
    text = clean_markdown_text(text)
    return re.sub(r"\s+", " ", text).strip()


def html_to_markdownish(text: str) -> str:
    text = re.sub(r"</?(?:p|div|section|article)[^>]*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<h([1-6])[^>]*>(.*?)</h\1>", lambda match: f"\n\n{'#' * int(match.group(1))} {match.group(2)}\n\n", text, flags=re.IGNORECASE | re.DOTALL)
    return clean_markdown_text(_HTML_TAG_RE.sub("", text))
