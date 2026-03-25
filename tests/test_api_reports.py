import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_list_reports(client):
    mock_data = [
        {"id": "r1", "report_date": "2026-03-24", "content": {}, "created_at": None}
    ]
    with patch(
        "app.services.bridge.list_reports",
        new=AsyncMock(return_value=mock_data),
    ):
        resp = client.get("/api/reports")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_get_report_not_found(client):
    with patch(
        "app.services.bridge.get_report",
        new=AsyncMock(return_value=None),
    ):
        resp = client.get("/api/reports/nonexistent")
    assert resp.status_code == 404


def test_list_events(client):
    mock_data = [{"id": "e1", "title": "Test Event", "status": "active"}]
    with patch(
        "app.services.bridge.list_events",
        new=AsyncMock(return_value=mock_data),
    ):
        resp = client.get("/api/events")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_list_sources(client):
    mock_data = [{"name": "BBC", "url": "https://bbc.com", "tier": 1, "ok": True}]
    with patch(
        "app.services.bridge.get_source_statuses",
        new=AsyncMock(return_value=mock_data),
    ):
        resp = client.get("/api/sources")
    assert resp.status_code == 200
    assert resp.json()[0]["name"] == "BBC"


def test_system_status(client):
    resp = client.get("/api/system/status")
    assert resp.status_code == 200
    assert "uptime_seconds" in resp.json()
