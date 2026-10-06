# -*- coding: utf-8 -*-
"""
test_p4_hardening.py — Unit Tests for Production Hardening & Resilience (Phase 4)
Tests health monitor diagnostic, account auto-suspension, cluster leak protection,
reporting queries, and CSV export endpoints.
"""
import os
import sqlite3
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from buff_sub.health_monitor import (
    analyze_driver_health,
    suspend_account,
    check_cluster_health_and_protect,
    HEALTHY,
    SESSION_EXPIRED,
    PHONE_VERIFY_REQUIRED,
    ACTION_BLOCKED,
    BOT_CAPTCHA,
)
from buff_sub.database import (
    init_db,
    create_order,
    log_sub_attempt,
    get_order_summary,
    get_order_history,
    get_order_export_data,
)
from buff_sub.api.app import app


@pytest.fixture
def mock_shared_db(tmp_path):
    """Create a temporary shared database for health monitor tests."""
    db_file = str(tmp_path / "test_shared_pool.db")
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE gpm_profiles (
        id              TEXT PRIMARY KEY,
        gmail           TEXT NOT NULL,
        proxy           TEXT,
        is_active       INTEGER DEFAULT 1,
        last_used_at    TEXT,
        notes           TEXT
    );
    """)

    cur.execute("""
    CREATE TABLE sub_accounts (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        gpm_profile_id  TEXT NOT NULL,
        account_type    TEXT NOT NULL,
        channel_id      TEXT,
        channel_url     TEXT,
        switch_name     TEXT,
        niche           TEXT DEFAULT 'general',
        warmup_status   TEXT DEFAULT 'ready',
        warmup_days     INTEGER DEFAULT 14,
        warmup_videos   INTEGER DEFAULT 30,
        warmup_since    TEXT,
        ready_since     TEXT,
        total_subs_done INTEGER DEFAULT 0,
        subs_this_month INTEGER DEFAULT 0,
        last_sub_at     TEXT,
        cooldown_until  TEXT,
        is_active       INTEGER DEFAULT 1,
        created_at      TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(gpm_profile_id) REFERENCES gpm_profiles(id)
    );
    """)

    cur.execute("""
    CREATE TABLE account_locks (
        account_id      INTEGER PRIMARY KEY,
        locked_by       TEXT NOT NULL,
        locked_at       TEXT DEFAULT (datetime('now')),
        expires_at      TEXT NOT NULL,
        FOREIGN KEY(account_id) REFERENCES sub_accounts(id)
    );
    """)

    # Seed profile with 5 accounts
    cur.execute("INSERT INTO gpm_profiles (id, gmail, proxy, is_active) VALUES ('prof-cluster-1', 'lead@gmail.com', '127.0.0.1:8080', 1);")
    for i in range(1, 6):
        cur.execute(
            "INSERT INTO sub_accounts (id, gpm_profile_id, account_type, switch_name, warmup_status) VALUES (?, 'prof-cluster-1', 'brand_account', ?, 'ready');",
            (i, f"Brand {i}"),
        )

    # Put a lock on account #1
    cur.execute(
        "INSERT INTO account_locks (account_id, locked_by, locked_at, expires_at) VALUES (1, 'buff_sub', datetime('now'), datetime('now', '+30 minutes'));"
    )

    conn.commit()
    conn.close()
    return db_file


@pytest.fixture
def mock_local_db(tmp_path):
    """Create a temporary local orders database."""
    db_file = str(tmp_path / "test_local_buff.db")
    init_db(db_file)
    return db_file


# ── Test 1: Driver Health Analysis Patterns ───────────────────────

def test_analyze_driver_health_scenarios():
    # 1. Normal YouTube
    driver_ok = MagicMock()
    driver_ok.current_url = "https://www.youtube.com/watch?v=123"
    driver_ok.page_source = "<html><body>Standard video player</body></html>"
    status, reason = analyze_driver_health(driver_ok)
    assert status == HEALTHY
    assert reason is None

    # 2. Redirected to Google sign-in
    driver_signin = MagicMock()
    driver_signin.current_url = "https://accounts.google.com/signin/v2/identifier"
    driver_signin.page_source = "<html><body>Sign in with your Google Account</body></html>"
    status, reason = analyze_driver_health(driver_signin)
    assert status == SESSION_EXPIRED
    assert "sign-in" in reason.lower()

    # 3. Phone verification
    driver_phone = MagicMock()
    driver_phone.current_url = "https://www.youtube.com"
    driver_phone.page_source = "<div>Verify your account. Standard rates apply.</div>"
    status, reason = analyze_driver_health(driver_phone)
    assert status == PHONE_VERIFY_REQUIRED

    # 4. Action blocked
    driver_blocked = MagicMock()
    driver_blocked.current_url = "https://www.youtube.com/@channel"
    driver_blocked.page_source = "<div>This action is not allowed. Please try again later.</div>"
    status, reason = analyze_driver_health(driver_blocked)
    assert status == ACTION_BLOCKED

    # 5. Bot CAPTCHA
    driver_bot = MagicMock()
    driver_bot.current_url = "https://www.google.com/sorry/index"
    driver_bot.page_source = "<div>Our systems have detected unusual traffic from your computer network</div>"
    status, reason = analyze_driver_health(driver_bot)
    assert status == BOT_CAPTCHA


# ── Test 2: Auto-Suspend & Lock Release ───────────────────────────

def test_suspend_account(mock_shared_db):
    # Account #1 starts with active lock and status 'ready'
    ok = suspend_account(1, reason="Test Action Blocked", db_path=mock_shared_db)
    assert ok is True

    conn = sqlite3.connect(mock_shared_db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Verify warmup_status is 'suspended'
    cur.execute("SELECT warmup_status FROM sub_accounts WHERE id = 1;")
    assert cur.fetchone()["warmup_status"] == "suspended"

    # Verify lock was released
    cur.execute("SELECT COUNT(*) FROM account_locks WHERE account_id = 1;")
    assert cur.fetchone()[0] == 0
    conn.close()


# ── Test 3: Cluster Leak Protection ───────────────────────────────

def test_cluster_protection_trigger(mock_shared_db):
    # Total accounts for prof-cluster-1 = 5
    # Threshold = 20% (1 account suspended triggers protection)

    # Case A: 0 suspended -> not triggered
    protected = check_cluster_health_and_protect("prof-cluster-1", threshold_ratio=0.20, db_path=mock_shared_db)
    assert protected is False

    # Suspend 1 account
    suspend_account(1, reason="Flagged by Google", db_path=mock_shared_db)

    # Case B: 1/5 = 20% suspended -> triggers cluster deactivation
    protected = check_cluster_health_and_protect("prof-cluster-1", threshold_ratio=0.20, db_path=mock_shared_db)
    assert protected is True

    # Verify profile is deactivated
    conn = sqlite3.connect(mock_shared_db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT is_active, notes FROM gpm_profiles WHERE id = 'prof-cluster-1';")
    profile = cur.fetchone()
    assert profile["is_active"] == 0
    assert "Cluster leak detected" in profile["notes"]
    conn.close()


# ── Test 4: Database Export & Summary Aggregation ─────────────────

def test_database_export_and_summary(mock_local_db):
    order_id = create_order(
        channel_url="https://youtube.com/@TargetTest",
        target_subs=10,
        daily_cap=5,
        db_path=mock_local_db,
    )

    # Log 3 attempts: 2 successes, 1 failure
    log_sub_attempt(order_id, account_id=1, channel_id="@TargetTest", watch_seconds=120, did_like=True, sub_success=True, db_path=mock_local_db)
    log_sub_attempt(order_id, account_id=2, channel_id="@TargetTest", watch_seconds=90, did_like=False, sub_success=True, db_path=mock_local_db)
    log_sub_attempt(order_id, account_id=3, channel_id="@TargetTest", watch_seconds=30, did_like=False, sub_success=False, fail_reason="Network Timeout", db_path=mock_local_db)

    # Test summary
    summary = get_order_summary(order_id, db_path=mock_local_db)
    assert summary is not None
    assert summary["order_id"] == order_id
    assert summary["target_subs"] == 10
    assert summary["delivered"] == 2
    assert summary["total_attempts"] == 3
    assert summary["successful_subs"] == 2
    assert summary["failed_attempts"] == 1
    assert summary["success_rate_percent"] == 66.67
    assert summary["total_likes"] == 1
    assert summary["unique_accounts_count"] == 3

    # Test export data
    export_rows = get_order_export_data(order_id, db_path=mock_local_db)
    assert len(export_rows) == 3
    assert export_rows[0]["account_id"] == 1
    assert export_rows[0]["sub_success"] == 1
    assert export_rows[2]["fail_reason"] == "Network Timeout"

    # Test history
    hist = get_order_history(order_id, limit=2, db_path=mock_local_db)
    assert len(hist) == 2


# ── Test 5: API Endpoints (CSV Export & Summary) ──────────────────

def test_api_order_export_and_summary():
    order_id = 99
    client = TestClient(app)

    with patch("buff_sub.api.routes_orders.get_order") as mock_get_order:
        mock_get_order.return_value = {
            "id": order_id,
            "channel_url": "https://youtube.com/@CsvChannel",
            "target_subs": 5,
            "delivered": 1,
            "status": "running",
        }

        with patch("buff_sub.api.routes_orders.get_order_summary") as mock_summary:
            mock_summary.return_value = {
                "order_id": order_id,
                "channel_url": "https://youtube.com/@CsvChannel",
                "delivered": 1,
                "target_subs": 5,
                "success_rate_percent": 100.0,
            }
            res_sum = client.get(f"/api/orders/{order_id}/summary")
            assert res_sum.status_code == 200
            assert res_sum.json()["success_rate_percent"] == 100.0

        with patch("buff_sub.api.routes_orders.get_order_export_data") as mock_export:
            mock_export.return_value = [
                {
                    "history_id": 1,
                    "executed_at": "2026-10-06 12:00:00",
                    "account_id": 10,
                    "channel_id": "@CsvChannel",
                    "sub_success": 1,
                    "watch_seconds": 150,
                    "did_like": 1,
                    "fail_reason": None,
                }
            ]
            res_exp = client.get(f"/api/orders/{order_id}/export")
            assert res_exp.status_code == 200
            assert "text/csv" in res_exp.headers["content-type"]
            assert f"order_{order_id}_export.csv" in res_exp.headers["content-disposition"]
            csv_body = res_exp.text
            assert "history_id,executed_at,account_id" in csv_body
            assert "10,@CsvChannel,1,150,1" in csv_body

