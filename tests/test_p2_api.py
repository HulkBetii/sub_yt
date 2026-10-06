# -*- coding: utf-8 -*-
"""
tests/test_p2_api.py — Unit Tests for FastAPI REST Endpoints
Verifies order CRUD lifecycle, state transitions (pause/resume), scheduler APIs,
and system status routes using TestClient.
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from buff_sub.api.app import app
from buff_sub.database import init_db


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Setup an isolated TestClient with temporary databases."""
    local_db = str(tmp_path / "api_test_buff_sub.db")
    shared_db = str(tmp_path / "api_test_account_pool.db")

    init_db(local_db)
    monkeypatch.setattr("buff_sub.database.LOCAL_DB_PATH", local_db)
    monkeypatch.setattr("buff_sub.config.LOCAL_DB_PATH", local_db)

    with TestClient(app) as test_client:
        yield test_client


def test_api_health_endpoint(client):
    """Verify healthcheck endpoint returns status 200 and ok."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "buff-sub-yt Engine" in data["service"]


def test_api_orders_crud_flow(client):
    """Verify complete CRUD lifecycle of orders via REST API."""
    # 1. Create Order
    create_payload = {
        "channel_url": "https://www.youtube.com/@APITestChannel",
        "target_subs": 30,
        "daily_cap": 15,
        "priority": 3,
        "customer_note": "REST API Test Order",
    }
    resp = client.post("/api/orders", json=create_payload)
    assert resp.status_code == 201
    ord_data = resp.json()
    order_id = ord_data["id"]
    assert ord_data["channel_id"] == "@APITestChannel"
    assert ord_data["target_subs"] == 30
    assert ord_data["daily_cap"] == 15
    assert ord_data["status"] == "pending"
    assert ord_data["effective_daily_cap"] is not None

    # 2. Get Order Detail
    resp_get = client.get(f"/api/orders/{order_id}")
    assert resp_get.status_code == 200
    assert resp_get.json()["id"] == order_id

    # 3. List Orders
    resp_list = client.get("/api/orders")
    assert resp_list.status_code == 200
    assert resp_list.json()["total"] >= 1

    # 4. Pause Order
    resp_pause = client.post(f"/api/orders/{order_id}/pause")
    assert resp_pause.status_code == 200
    assert resp_pause.json()["status"] == "paused"

    # 5. Resume Order
    resp_resume = client.post(f"/api/orders/{order_id}/resume")
    assert resp_resume.status_code == 200
    assert resp_resume.json()["status"] == "running"

    # 6. Delete Order
    resp_del = client.delete(f"/api/orders/{order_id}")
    assert resp_del.status_code == 200
    assert resp_del.json()["status"] == "deleted"

    # 7. Confirm 404 after deletion
    resp_after = client.get(f"/api/orders/{order_id}")
    assert resp_after.status_code == 404


def test_api_order_validation_errors(client):
    """Verify invalid payloads return HTTP 422 Unprocessable Entity."""
    # Negative target subs
    bad_payload = {
        "channel_url": "https://www.youtube.com/@BadChan",
        "target_subs": -5,
        "daily_cap": 10,
    }
    resp = client.post("/api/orders", json=bad_payload)
    assert resp.status_code == 422


def test_api_scheduler_endpoints(client):
    """Verify scheduler status, pause, resume, and tick routes."""
    # 1. Status
    resp_status = client.get("/api/scheduler/status")
    assert resp_status.status_code == 200
    data = resp_status.json()
    assert "is_running" in data
    assert "is_paused" in data

    # 2. Pause
    resp_pause = client.post("/api/scheduler/pause")
    assert resp_pause.status_code == 200
    assert resp_pause.json()["is_paused"] is True

    # 3. Resume
    resp_resume = client.post("/api/scheduler/resume")
    assert resp_resume.status_code == 200
    assert resp_resume.json()["is_paused"] is False

    # 4. Trigger Tick (dry-run)
    with patch("buff_sub.api.routes_scheduler.trigger_tick_now") as mock_tick:
        mock_tick.return_value = {
            "status": "completed",
            "timestamp": "2026-10-06 12:00:00",
            "dry_run": True,
            "orders_checked": 0,
            "sessions_attempted": 0,
            "successful": 0,
            "details": [],
        }
        resp_tick = client.post("/api/scheduler/tick?dry_run=true")
        assert resp_tick.status_code == 200
        assert resp_tick.json()["dry_run"] is True


def test_api_system_routes(client):
    """Verify system metrics, accounts, and logs endpoints."""
    # Stats
    resp_stats = client.get("/api/stats")
    assert resp_stats.status_code == 200
    assert "orders" in resp_stats.json()

    # Accounts summary
    resp_accs = client.get("/api/accounts")
    assert resp_accs.status_code == 200

    # Accounts list
    resp_list = client.get("/api/accounts/list?limit=10")
    assert resp_list.status_code == 200
    assert "total" in resp_list.json()
    assert "accounts" in resp_list.json()

    # Logs
    resp_logs = client.get("/api/logs?limit=50")
    assert resp_logs.status_code == 200
    assert "lines" in resp_logs.json()


def test_frontend_dashboard_static_serve(client):
    """Verify built frontend dashboard index.html is served at root path /."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "buff-sub-yt Engine Dashboard" in resp.text

