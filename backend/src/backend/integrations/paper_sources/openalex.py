from __future__ import annotations

import httpx

from backend.schemas import PaperSearchResult


class OpenAlexClient:
    def __init__(self, *, api_key: str | None = None, email: str | None = None, timeout_seconds: float = 30.0) -> None:
        headers = {"User-Agent": "paper-claw"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self.email = email
        self.client = httpx.Client(base_url="https://api.openalex.org", headers=headers, timeout=timeout_seconds)

    def search(self, query: str, max_results: int = 10) -> list[PaperSearchResult]:
        params: dict[str, object] = {"search": query, "per-page": max(1, min(max_results, 50))}
        if self.email:
            params["mailto"] = self.email
        response = self.client.get("/works", params=params)
        response.raise_for_status()
        payload = response.json()
        return [self._to_search_result(item) for item in payload.get("results", [])]

    def _to_search_result(self, item: dict) -> PaperSearchResult:
        doi = item.get("doi")
        if isinstance(doi, str):
            doi = doi.removeprefix("https://doi.org/")
        authors = [
            authorship.get("author", {}).get("display_name", "")
            for authorship in item.get("authorships", [])
            if authorship.get("author", {}).get("display_name")
        ]
        primary_location = item.get("primary_location") or {}
        return PaperSearchResult(
            source="openalex",
            source_record_id=item.get("id"),
            title=item.get("title") or item.get("display_name") or "Untitled OpenAlex work",
            abstract=item.get("abstract_inverted_index") and _restore_abstract(item["abstract_inverted_index"]),
            authors=authors,
            year=item.get("publication_year"),
            venue=(primary_location.get("source") or {}).get("display_name"),
            doi=doi,
            openalex_id=item.get("id"),
            landing_page_url=primary_location.get("landing_page_url") or item.get("id"),
            pdf_url=primary_location.get("pdf_url"),
            raw=item,
        )


def _restore_abstract(inverted_index: dict[str, list[int]]) -> str:
    words: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        words.extend((position, word) for position in positions)
    return " ".join(word for _, word in sorted(words))
