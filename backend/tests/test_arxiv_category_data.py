from __future__ import annotations

import json
from pathlib import Path


CATEGORY_DATA_PATH = Path(__file__).resolve().parents[1] / "src" / "backend" / "data" / "arxiv_categories_flat.json"


def test_arxiv_category_data_contains_full_catalog():
    categories = json.loads(CATEGORY_DATA_PATH.read_text(encoding="utf-8"))

    assert len(categories) == 155
    assert len({item["code"] for item in categories}) == 155

    cs_lg = next(item for item in categories if item["code"] == "cs.LG")
    assert cs_lg["top_area"] == "Computer Science"
    assert cs_lg["group"] is None
    assert cs_lg["api_exact_query"] == "cat:cs.LG"

    physics = [item for item in categories if item["top_area"] == "Physics"]
    assert physics
    assert any(item["group"] and item["group_code"] for item in physics)
    assert any(item["is_alias"] and item["alias_of"] for item in categories)
