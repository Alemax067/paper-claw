from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.db.models import ArxivTaskSubscription
from backend.db.types import ArxivTaskJobStatus


def test_arxiv_task_status_includes_subscriptions(client, session):
    subscription = ArxivTaskSubscription(name="Machine learning", query="cat:cs.LG", description="ML query", enabled=True)
    session.add(subscription)
    session.commit()

    response = client.get("/api/tasks/arxiv/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled_subscription_ids"] == [subscription.id]
    assert payload["coverage_subscription_ids"] == []
    assert payload["daily_config"]["run_time"] == "08:00"
    item = payload["subscriptions"][0]
    assert item["name"] == "Machine learning"
    assert item["query"] == "cat:cs.LG"
    assert item["description"] == "ML query"
    assert item["enabled"] is True


def test_arxiv_task_subscription_create_preserves_query_source(client, session):
    response = client.post(
        "/api/tasks/arxiv/subscriptions",
        json={"name": "Agents", "query": "  cat:cs.AI AND (ti:agent OR abs:agent)  ", "description": None, "enabled": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "  cat:cs.AI AND (ti:agent OR abs:agent)  "


def test_arxiv_history_job_validates_unknown_subscription_id(client, session):
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=1)

    response = client.post(
        "/api/tasks/arxiv/history-jobs",
        json={"subscription_ids": [999], "start_time": start.isoformat(), "end_time": end.isoformat()},
    )

    assert response.status_code == 400


def test_arxiv_history_job_lifecycle(client, session):
    subscription = ArxivTaskSubscription(name="Machine learning", query="cat:cs.LG", enabled=False)
    session.add(subscription)
    session.commit()
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=1)

    create_response = client.post(
        "/api/tasks/arxiv/history-jobs",
        json={"subscription_ids": [subscription.id], "start_time": start.isoformat(), "end_time": end.isoformat()},
    )
    assert create_response.status_code == 200
    job_id = create_response.json()["id"]
    assert create_response.json()["status"] == ArxivTaskJobStatus.paused.value
    assert create_response.json()["subscription_ids"] == [subscription.id]

    start_response = client.post(f"/api/tasks/arxiv/history-jobs/{job_id}/start")
    assert start_response.status_code == 200
    assert start_response.json()["status"] == ArxivTaskJobStatus.running.value

    pause_response = client.post(f"/api/tasks/arxiv/history-jobs/{job_id}/pause")
    assert pause_response.status_code == 200
    assert pause_response.json()["status"] == ArxivTaskJobStatus.paused.value

    stop_response = client.post(f"/api/tasks/arxiv/history-jobs/{job_id}/stop")
    assert stop_response.status_code == 200
    assert stop_response.json()["status"] == ArxivTaskJobStatus.stopped.value
