# -*- coding: utf-8 -*-
"""
Unit test suite for Phase 1 Task 5 (P1.T5): Order Manager (order_manager.py).
Tests daily/hourly slot calculations, Master Gmail Diversity filtering,
Anti-Clustering rate limiting, and order execution dispatch.
"""
import os
import sys
import sqlite3
import pytest
from unittest.mock import patch, MagicMock

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from buff_sub.database import init_db as init_local_db, create_order, update_order_status, log_sub_attempt
from buff_sub.order_manager import (
    calculate_order_slots_today,
    assign_accounts_to_order,
    process_order,
)


@pytest.fixture
def mock_dbs(tmp_path):
    """Fixture creating both local buff_sub.db and shared account_pool.db."""
    local_db = str(tmp_path / "mock_buff_sub.db")
    shared_db = str(tmp_path / "mock_account_pool.db")

    # 1. Initialize local DB
    init_local_db(local_db)

    # 2. Initialize shared DB
    s_conn = sqlite3.connect(shared_db)
    s_cur = s_conn.cursor()
    s_cur.execute("""
    CREATE TABLE gpm_profiles (
        id TEXT PRIMARY KEY,
        gmail TEXT NOT NULL,
        proxy TEXT,
        is_active INTEGER DEFAULT 1,
        last_used_at TEXT,
        notes TEXT
    );
    """)
    s_cur.execute("""
    CREATE TABLE sub_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        gpm_profile_id TEXT NOT NULL,
        account_type TEXT NOT NULL,
        channel_id TEXT UNIQUE,
        switch_name TEXT,
        warmup_status TEXT DEFAULT 'ready',
        total_subs_done INTEGER DEFAULT 0,
        subs_this_month INTEGER DEFAULT 0,
        last_sub_at TEXT,
        cooldown_until TEXT,
        is_active INTEGER DEFAULT 1,
        FOREIGN KEY(gpm_profile_id) REFERENCES gpm_profiles(id)
    );
    """)
    s_cur.execute("""
    CREATE TABLE account_locks (
        account_id INTEGER PRIMARY KEY,
        locked_by TEXT NOT NULL,
        locked_at TEXT DEFAULT (datetime('now')),
        expires_at TEXT NOT NULL
    );
    """)

    # Seed 3 GPM Profiles
    s_cur.execute("INSERT INTO gpm_profiles (id, gmail) VALUES ('gpm-A', 'userA@gmail.com');")
    s_cur.execute("INSERT INTO gpm_profiles (id, gmail) VALUES ('gpm-B', 'userB@gmail.com');")
    s_cur.execute("INSERT INTO gpm_profiles (id, gmail) VALUES ('gpm-C', 'userC@gmail.com');")

    # Seed 2 accounts for gpm-A, 1 for gpm-B, 1 for gpm-C
    s_cur.execute("INSERT INTO sub_accounts (id, gpm_profile_id, account_type, channel_id, warmup_status) VALUES (1, 'gpm-A', 'gmail_root', '@chan_A1', 'ready');")
    s_cur.execute("INSERT INTO sub_accounts (id, gpm_profile_id, account_type, channel_id, warmup_status) VALUES (2, 'gpm-A', 'brand_account', '@chan_A2', 'ready');")
    s_cur.execute("INSERT INTO sub_accounts (id, gpm_profile_id, account_type, channel_id, warmup_status) VALUES (3, 'gpm-B', 'gmail_root', '@chan_B1', 'ready');")
    s_cur.execute("INSERT INTO sub_accounts (id, gpm_profile_id, account_type, channel_id, warmup_status) VALUES (4, 'gpm-C', 'brand_account', '@chan_C1', 'ready');")

    s_conn.commit()
    s_conn.close()

    return {"local": local_db, "shared": shared_db}


def test_calculate_order_slots_today(mock_dbs):
    """Verify calculation of available daily slots under different conditions."""
    local_db = mock_dbs["local"]

    # 1. Normal order with plenty remaining
    ord1 = create_order("https://www.youtube.com/@Chan1", target_subs=50, daily_cap=10, db_path=local_db)
    assert calculate_order_slots_today(ord1, db_path=local_db) == 10

    # 2. Order where remaining target is smaller than daily cap
    ord2 = create_order("https://www.youtube.com/@Chan2", target_subs=3, daily_cap=10, db_path=local_db)
    assert calculate_order_slots_today(ord2, db_path=local_db) == 3

    # 3. Order where today's delivered quota is partially filled
    log_sub_attempt(ord1, account_id=99, channel_id="@Chan1", sub_success=True, db_path=local_db)
    # Target now 49 remaining, daily quota: 10 - 1 = 9
    assert calculate_order_slots_today(ord1, db_path=local_db) == 9

    # 4. Completed order returns 0
    update_order_status(ord1, status="completed", db_path=local_db)
    assert calculate_order_slots_today(ord1, db_path=local_db) == 0

    # 5. Paused order returns 0
    update_order_status(ord2, status="paused", db_path=local_db)
    assert calculate_order_slots_today(ord2, db_path=local_db) == 0


def test_assign_accounts_master_diversity(mock_dbs):
    """
    Verify Master Gmail Diversity: two accounts from gpm-A should never be assigned together.
    Candidate pool has acc 1 (gpm-A), acc 2 (gpm-A), acc 3 (gpm-B), acc 4 (gpm-C).
    When requesting 2 accounts, it should pick acc 1 (gpm-A) and acc 3 (gpm-B), skipping acc 2.
    """
    local_db = mock_dbs["local"]
    shared_db = mock_dbs["shared"]

    ord_id = create_order("https://www.youtube.com/@DiversityChan", target_subs=10, daily_cap=5, db_path=local_db)

    assigned = assign_accounts_to_order(
        order_id=ord_id,
        max_slots=2,
        shared_db_path=shared_db,
        local_db_path=local_db,
    )

    assert len(assigned) == 2
    gpm_ids = [a["gpm_profile_id"] for a in assigned]
    # Ensure all gpm_profile_ids in the batch are distinct
    assert len(gpm_ids) == len(set(gpm_ids))
    assert "gpm-A" in gpm_ids
    assert "gpm-B" in gpm_ids


def test_assign_accounts_already_subbed_filtering(mock_dbs):
    """Verify that an account that already subbed this channel is bypassed."""
    local_db = mock_dbs["local"]
    shared_db = mock_dbs["shared"]
    channel = "@DuplicateCheckChan"

    ord_id = create_order(f"https://www.youtube.com/{channel}", target_subs=10, daily_cap=5, db_path=local_db)

    # Log successful sub by account 1 in the past
    log_sub_attempt(order_id=ord_id, account_id=1, channel_id=channel, sub_success=True, db_path=local_db)

    # Request accounts: account 1 must be skipped, account 2 (also gpm-A) should be picked instead
    assigned = assign_accounts_to_order(
        order_id=ord_id,
        max_slots=2,
        shared_db_path=shared_db,
        local_db_path=local_db,
    )

    acc_ids = [a["id"] for a in assigned]
    assert 1 not in acc_ids
    assert 2 in acc_ids


def test_assign_accounts_hourly_velocity_limit(mock_dbs):
    """Verify that reaching 3 subs in the past hour postpones allocation."""
    local_db = mock_dbs["local"]
    shared_db = mock_dbs["shared"]
    channel = "@VelocityChan"

    ord_id = create_order(f"https://www.youtube.com/{channel}", target_subs=10, daily_cap=10, db_path=local_db)

    # Simulate 3 successful subs in the last hour
    for i in range(101, 104):
        log_sub_attempt(order_id=ord_id, account_id=i, channel_id=channel, sub_success=True, db_path=local_db)

    # Hourly cap reached (3/3), assign must return empty list
    assigned = assign_accounts_to_order(
        order_id=ord_id,
        max_slots=2,
        shared_db_path=shared_db,
        local_db_path=local_db,
    )
    assert assigned == []


@patch("buff_sub.order_manager.run_sub_session")
def test_process_order_dry_run(mock_run_sub, mock_dbs):
    """Verify process_order execution with dry_run mode."""
    local_db = mock_dbs["local"]
    shared_db = mock_dbs["shared"]

    ord_id = create_order("https://www.youtube.com/@DryProcessChan", target_subs=10, daily_cap=5, db_path=local_db)

    mock_run_sub.return_value = {
        "order_id": ord_id,
        "account_id": 1,
        "sub_success": True,
        "did_like": True,
        "watch_seconds": 95,
        "dry_run": True,
    }

    summary = process_order(
        order_id=ord_id,
        max_subs=2,
        dry_run=True,
        shared_db_path=shared_db,
        local_db_path=local_db,
    )

    assert summary["order_id"] == ord_id
    assert summary["dry_run"] is True
    assert summary["assigned_count"] == 2
    assert summary["successful_count"] == 2
    assert len(summary["session_results"]) == 2
    assert mock_run_sub.call_count == 2


@patch("buff_sub.order_manager.run_sub_session")
@patch("time.sleep")  # Mock time.sleep to avoid waiting for inter-session jitter
def test_process_order_live_execution(mock_sleep, mock_run_sub, mock_dbs):
    """Verify process_order handles live execution flow."""
    local_db = mock_dbs["local"]
    shared_db = mock_dbs["shared"]

    ord_id = create_order("https://www.youtube.com/@LiveProcessChan", target_subs=10, daily_cap=5, db_path=local_db)

    mock_run_sub.return_value = {
        "order_id": ord_id,
        "account_id": 1,
        "sub_success": True,
        "did_like": True,
        "watch_seconds": 120,
        "dry_run": False,
    }

    summary = process_order(
        order_id=ord_id,
        max_subs=1,
        dry_run=False,
        shared_db_path=shared_db,
        local_db_path=local_db,
    )

    assert summary["successful_count"] == 1
    assert summary["failed_count"] == 0
    mock_run_sub.assert_called_once()
