from __future__ import annotations

from typing import Protocol

from backend.schemas import PaperSearchResult


class PaperSourceAdapter(Protocol):
    def search(self, query: str, max_results: int = 10) -> list[PaperSearchResult]:
        ...
