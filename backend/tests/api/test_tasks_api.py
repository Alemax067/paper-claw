from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.db.models import ArxivTaskCategory
from backend.db.types import ArxivTaskJobStatus


def test_arxiv_task_status_includes_categories(client, session):
    session.add(ArxivTaskCategory(cat_id="cs.LG", top_area="Computer Science", group=None, group_code=None, archive="cs", name="Machine Learning", is_alias=False, alias_of=None, api_exact_query="cat:cs.LG", enabled=True))
    session.commit()

    response = client.get("/api/tasks/arxiv/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled_cat_ids"] == ["cs.LG"]
    assert payload["daily_config"]["run_time"] == "08:00"
    category = payload["categories"][0]
    assert category["top_area"] == "Computer Science"
    assert category["group"] is None
    assert category["group_code"] is None
    assert category["is_alias"] is False
    assert category["alias_of"] is None
    assert category["api_exact_query"] == "cat:cs.LG"


def test_arxiv_task_category_update_validates_unknown_cat_id(client, session):
    session.add(ArxivTaskCategory(cat_id="cs.LG", top_area="Computer Science", group=None, group_code=None, archive="cs", name="Machine Learning", is_alias=False, alias_of=None, api_exact_query="cat:cs.LG", enabled=False))
    session.commit()

    response = client.put("/api/tasks/arxiv/categories", json={"enabled_cat_ids": ["cs.UNKNOWN"]})

    assert response.status_code == 400


def test_arxiv_history_job_lifecycle(client, session):
    session.add(ArxivTaskCategory(cat_id="cs.LG", top_area="Computer Science", group=None, group_code=None, archive="cs", name="Machine Learning", is_alias=False, alias_of=None, api_exact_query="cat:cs.LG", enabled=False))
    session.commit()
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=1)

    create_response = client.post(
        "/api/tasks/arxiv/history-jobs",
        json={"cat_ids": ["cs.LG"], "start_time": start.isoformat(), "end_time": end.isoformat()},
    )
    assert create_response.status_code == 200
    job_id = create_response.json()["id"]
    assert create_response.json()["status"] == ArxivTaskJobStatus.paused.value

    start_response = client.post(f"/api/tasks/arxiv/history-jobs/{job_id}/start")
    assert start_response.status_code == 200
    assert start_response.json()["status"] == ArxivTaskJobStatus.running.value

    pause_response = client.post(f"/api/tasks/arxiv/history-jobs/{job_id}/pause")
    assert pause_response.status_code == 200
    assert pause_response.json()["status"] == ArxivTaskJobStatus.paused.value

    stop_response = client.post(f"/api/tasks/arxiv/history-jobs/{job_id}/stop")
    assert stop_response.status_code == 200
    assert stop_response.json()["status"] == ArxivTaskJobStatus.stopped.value
