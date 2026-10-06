# -*- coding: utf-8 -*-
"""
tests/test_p2_scheduler.py — Unit Tests for Autonomous Scheduler Layer
Verifies periodic tick dispatching, velocity filtering, pause/resume state,
and re-entrancy guardrails.
"""
import pytest
import sqlite3
import datetime
from unittest.mock import patch, MagicMock

from buff_sub.database import (
    init_db,
    create_order,
    update_order_status,
    log_sub_attempt,
)
from buff_sub.scheduler import (
    drip_feed_tick,
    start_scheduler,
    stop_scheduler,
    pause_scheduler,
    resume_scheduler,
    get_scheduler_status,
    trigger_tick_now,
    _tick_lock,
)


@pytest.fixture
def mock_dbs(tmp_path):
    """Create isolated mock database files for scheduler tests."""
    local_db = str(tmp_path / "mock_buff_sub.db")
    shared_db = str(tmp_path / "mock_account_pool.db")

    init_db(local_db)

    # Initialize shared mock account pool
    s_conn = sqlite3.connect(shared_db)
    s_cur = s_conn.cursor()
    s_cur.execute("""
    CREATE TABLE gpm_profiles (
        id TEXT PRIMARY KEY,
        name TEXT,
        profile_path TEXT,
        proxy_raw TEXT,
        status TEXT DEFAULT 'active'
    );
    """)
    s_cur.execute("""
    CREATE TABLE sub_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        gpm_profile_id TEXT NOT NULL,
        account_type TEXT DEFAULT 'gmail_root',
        channel_id TEXT,
        channel_name TEXT,
        switch_name TEXT,
        niche TEXT DEFAULT 'general',
        warmup_status TEXT DEFAULT 'ready',
        warmup_days INTEGER DEFAULT 0,
        warmup_videos INTEGER DEFAULT 0,
        warmup_since TEXT,
        ready_since TEXT,
        cooldown_until TEXT,
        subs_this_month INTEGER DEFAULT 0,
        last_sub_at TEXT,
        is_active INTEGER DEFAULT 1
    );
    """)
    s_cur.execute("""
    CREATE TABLE account_locks (
        account_id INTEGER PRIMARY KEY,
        locked_by TEXT,
        locked_at TEXT,
        expires_at TEXT
    );
    """)

    # Seed 2 profiles and accounts
    s_cur.execute("INSERT INTO gpm_profiles (id, name) VALUES ('gpm-1', 'Profile 1');")
    s_cur.execute("INSERT INTO gpm_profiles (id, name) VALUES ('gpm-2', 'Profile 2');")

    s_cur.execute("INSERT INTO sub_accounts (id, gpm_profile_id, account_type, warmup_status) VALUES (1, 'gpm-1', 'gmail_root', 'ready');")
    s_cur.execute("INSERT INTO sub_accounts (id, gpm_profile_id, account_type, warmup_status) VALUES (2, 'gpm-2', 'gmail_root', 'ready');")

    s_conn.commit()
    s_conn.close()

    yield {"local": local_db, "shared": shared_db}

    # Clean up scheduler after test
    stop_scheduler()


def test_drip_feed_tick_no_orders(mock_dbs):
    """Verify that a routine tick cleanly finishes when no orders are running."""
    local_db = mock_dbs["local"]
    shared_db = mock_dbs["shared"]

    res = drip_feed_tick(dry_run=True, local_db_path=local_db, shared_db_path=shared_db)
    assert res["status"] == "completed"
    assert res["orders_checked"] == 0
    assert res["sessions_attempted"] == 0


@patch("buff_sub.scheduler.process_order")
def test_drip_feed_tick_executes_running_order(mock_process, mock_dbs):
    """Verify that a routine tick dispatches 1 drip-feed slot for a running order."""
    local_db = mock_dbs["local"]
    shared_db = mock_dbs["shared"]

    ord_id = create_order("https://www.youtube.com/@SchedTarget", target_subs=20, daily_cap=10, db_path=local_db)
    update_order_status(ord_id, "running", db_path=local_db)

    mock_process.return_value = {
        "order_id": ord_id,
        "status": "success",
        "assigned_count": 1,
        "successful_count": 1,
    }

    res = drip_feed_tick(dry_run=True, local_db_path=local_db, shared_db_path=shared_db)

    assert res["status"] == "completed"
    assert res["orders_checked"] == 1
    assert res["sessions_attempted"] == 1
    assert res["successful"] == 1

    mock_process.assert_called_once_with(
        order_id=ord_id,
        max_subs=1,
        dry_run=True,
        shared_db_path=shared_db,
        local_db_path=local_db,
        apply_drip_feed=True,
    )


def test_drip_feed_tick_skips_when_hourly_velocity_reached(mock_dbs):
    """Verify that orders exceeding 3 subs/hour are safely skipped during the tick."""
    local_db = mock_dbs["local"]
    shared_db = mock_dbs["shared"]

    channel = "@VelocityCapChan"
    ord_id = create_order(f"https://www.youtube.com/{channel}", target_subs=20, daily_cap=10, db_path=local_db)
    update_order_status(ord_id, "running", db_path=local_db)

    # Simulate 3 successful subs within the last 60 minutes
    for acc in [101, 102, 103]:
        log_sub_attempt(ord_id, account_id=acc, channel_id=channel, sub_success=True, db_path=local_db)

    res = drip_feed_tick(dry_run=True, local_db_path=local_db, shared_db_path=shared_db)

    assert res["orders_checked"] == 1
    assert res["sessions_attempted"] == 0
    assert any(d["action"] == "skip" and "Hourly velocity cap reached" in d["reason"] for d in res["details"])


def test_drip_feed_tick_reentrancy_lock(mock_dbs):
    """Verify that a tick request aborts cleanly if another tick is actively running."""
    local_db = mock_dbs["local"]
    shared_db = mock_dbs["shared"]

    # Acquire the re-entrancy lock artificially
    acquired = _tick_lock.acquire(blocking=False)
    assert acquired is True

    try:
        res = drip_feed_tick(dry_run=True, local_db_path=local_db, shared_db_path=shared_db)
        assert res["status"] == "busy"
        assert "Previous tick still running" in res["reason"]
    finally:
        _tick_lock.release()


def test_scheduler_lifecycle_and_status(mock_dbs):
    """Verify start, pause, resume, status inspection and shutdown."""
    local_db = mock_dbs["local"]
    shared_db = mock_dbs["shared"]

    # 1. Start scheduler
    started = start_scheduler(tick_minutes=30, dry_run=True, local_db_path=local_db, shared_db_path=shared_db)
    assert started is True

    status = get_scheduler_status()
    assert status["is_running"] is True
    assert status["is_paused"] is False
    assert status["active_jobs_count"] >= 1

    # 2. Pause
    pause_scheduler()
    status_p = get_scheduler_status()
    assert status_p["is_paused"] is True

    # When paused, tick should be skipped
    tick_res = drip_feed_tick(dry_run=True, local_db_path=local_db, shared_db_path=shared_db)
    assert tick_res["status"] == "paused"

    # 3. Resume
    resume_scheduler()
    status_r = get_scheduler_status()
    assert status_r["is_paused"] is False

    # 4. Stop
    stopped = stop_scheduler()
    assert stopped is True
    status_s = get_scheduler_status()
    assert status_s["is_running"] is False


def test_circadian_sleep_guard_and_tick_skipping(mock_dbs):
    """Verify circadian rhythm sleep detection and tick suspension during night hours."""
    from buff_sub.scheduler import is_circadian_sleep_time

    # Test when mock local time is 03:00 (middle of deep sleep)
    with patch("buff_sub.scheduler.datetime") as mock_dt:
        mock_now = datetime.datetime(2026, 10, 6, 20, 0, 0)  # UTC 20:00 + 7h = 03:00 local
        mock_dt.datetime.utcnow.return_value = mock_now
        mock_dt.timedelta = datetime.timedelta

        assert is_circadian_sleep_time() is True

        res = drip_feed_tick(dry_run=False, local_db_path=mock_dbs["local"], shared_db_path=mock_dbs["shared"])
        assert res["status"] == "sleep_hours"


def test_warmup_routine_tick_dry_run(mock_dbs):
    """Verify autonomous warmup routine tick discovers and processes candidate brand accounts."""
    from buff_sub.scheduler import warmup_routine_tick

    shared_db = mock_dbs["shared"]
    s_conn = sqlite3.connect(shared_db)
    s_cur = s_conn.cursor()

    # Add candidate brand accounts
    s_cur.execute("UPDATE gpm_profiles SET name = 'sub_yt-1' WHERE id = 'gpm-1';")
    s_cur.execute("""
        INSERT INTO sub_accounts (gpm_profile_id, account_type, switch_name, niche, warmup_status, warmup_videos, is_active)
        VALUES ('gpm-1', 'brand_account', 'Test Brand 1', 'gaming', 'cold', 0, 1);
    """)
    s_conn.commit()
    s_conn.close()

    res = warmup_routine_tick(dry_run=True, shared_db_path=shared_db)
    assert res["status"] == "completed"
    assert res["accounts_processed"] >= 1
    assert res["successful"] >= 1
    assert res["details"][0]["status"] == "dry_run_success"


def test_maintenance_routine_tick_cleans_expired_locks(mock_dbs):
    """Verify maintenance tick cleans up expired locks in account_locks table."""
    from buff_sub.scheduler import maintenance_routine_tick

    shared_db = mock_dbs["shared"]
    s_conn = sqlite3.connect(shared_db)
    s_cur = s_conn.cursor()

    # Add expired lock
    s_cur.execute("""
        INSERT INTO account_locks (account_id, locked_by, locked_at, expires_at)
        VALUES (1, 'old_proc', datetime('now', '-10 minutes'), datetime('now', '-5 minutes'));
    """)
    s_conn.commit()
    s_conn.close()

    res = maintenance_routine_tick(shared_db_path=shared_db)
    assert res["status"] == "completed"
    assert res["cleared_locks"] == 1

