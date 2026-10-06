# -*- coding: utf-8 -*-
"""
Unit test suite for Phase 1 Task 2 (P1.T2): Internal Database Layer (database.py).
Tests orders lifecycle, execution audit history, WAL mode, and anti-clustering queries.
"""
import os
import sys
import sqlite3
import pytest

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from buff_sub.database import (
    extract_channel_id,
    init_db,
    create_order,
    get_order,
    list_orders,
    update_order_status,
    increment_order_delivered,
    log_sub_attempt,
    get_sub_history,
    has_account_subbed,
    get_delivered_today,
    get_subs_last_hour,
    get_order_stats,
)


@pytest.fixture
def temp_db(tmp_path):
    """Fixture providing a temporary SQLite database path."""
    db_file = str(tmp_path / "test_buff_sub.db")
    init_db(db_file)
    return db_file


def test_extract_channel_id():
    """Verify channel handle and ID extraction from various YouTube URL formats."""
    assert extract_channel_id("https://www.youtube.com/@TechLead") == "@TechLead"
    assert extract_channel_id("https://youtube.com/@channel.test-1") == "@channel.test-1"
    assert extract_channel_id("https://www.youtube.com/channel/UC_x5XG1OV2P6uZZ5FSM9Ttw") == "UC_x5XG1OV2P6uZZ5FSM9Ttw"
    assert extract_channel_id("https://www.youtube.com/c/CustomName") == "CustomName"
    assert extract_channel_id("@DirectHandle") == "@DirectHandle"


def test_init_db_creates_schema_and_indexes(temp_db):
    """Verify that tables and indexes are properly created with WAL mode."""
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()

    # Verify tables
    tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
    assert "orders" in tables
    assert "sub_history" in tables

    # Verify indexes
    indexes = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='index';").fetchall()]
    assert "idx_orders_status" in indexes
    assert "idx_sub_history_order" in indexes
    assert "idx_sub_history_account" in indexes
    assert "idx_sub_history_channel" in indexes

    # Verify WAL mode
    journal_mode = cursor.execute("PRAGMA journal_mode;").fetchone()[0]
    assert journal_mode.lower() == "wal"

    conn.close()


def test_order_crud_lifecycle(temp_db):
    """Verify order creation, retrieval, listing, and status updates."""
    # Create order
    order_id = create_order(
        channel_url="https://www.youtube.com/@MyChannel",
        target_subs=50,
        daily_cap=10,
        priority=3,
        customer_note="VIP customer",
        db_path=temp_db,
    )
    assert order_id > 0

    # Retrieve order
    order = get_order(order_id, db_path=temp_db)
    assert order is not None
    assert order["id"] == order_id
    assert order["channel_url"] == "https://www.youtube.com/@MyChannel"
    assert order["channel_id"] == "@MyChannel"
    assert order["target_subs"] == 50
    assert order["daily_cap"] == 10
    assert order["delivered"] == 0
    assert order["status"] == "pending"
    assert order["priority"] == 3
    assert order["customer_note"] == "VIP customer"
    assert order["completed_at"] is None

    # Update order status
    assert update_order_status(order_id, "running", db_path=temp_db) is True
    updated = get_order(order_id, db_path=temp_db)
    assert updated["status"] == "running"

    # List orders
    all_orders = list_orders(db_path=temp_db)
    assert len(all_orders) == 1
    assert all_orders[0]["id"] == order_id

    # Filter orders by status
    running_orders = list_orders(status="running", db_path=temp_db)
    assert len(running_orders) == 1
    completed_orders = list_orders(status="completed", db_path=temp_db)
    assert len(completed_orders) == 0


def test_sub_history_and_auto_completion(temp_db):
    """Verify logging attempts and automatic completion when delivered reaches target."""
    target = 2
    order_id = create_order(
        channel_url="https://www.youtube.com/@GoalChannel",
        target_subs=target,
        db_path=temp_db,
    )

    # 1. Failed attempt
    h1 = log_sub_attempt(
        order_id=order_id,
        account_id=101,
        channel_id="@GoalChannel",
        watch_seconds=45,
        did_like=False,
        sub_success=False,
        fail_reason="Subscribe button not found",
        db_path=temp_db,
    )
    assert h1 > 0
    ord_after_fail = get_order(order_id, db_path=temp_db)
    assert ord_after_fail["delivered"] == 0
    assert ord_after_fail["status"] == "pending"

    # 2. Successful attempt #1
    h2 = log_sub_attempt(
        order_id=order_id,
        account_id=102,
        channel_id="@GoalChannel",
        watch_seconds=120,
        did_like=True,
        sub_success=True,
        db_path=temp_db,
    )
    assert h2 > 0
    ord_step1 = get_order(order_id, db_path=temp_db)
    assert ord_step1["delivered"] == 1
    assert ord_step1["status"] == "running"
    assert ord_step1["completed_at"] is None

    # 3. Successful attempt #2 (Target reached)
    h3 = log_sub_attempt(
        order_id=order_id,
        account_id=103,
        channel_id="@GoalChannel",
        watch_seconds=150,
        did_like=True,
        sub_success=True,
        db_path=temp_db,
    )
    assert h3 > 0
    ord_step2 = get_order(order_id, db_path=temp_db)
    assert ord_step2["delivered"] == 2
    assert ord_step2["status"] == "completed"
    assert ord_step2["completed_at"] is not None

    # Verify history list
    history = get_sub_history(order_id=order_id, db_path=temp_db)
    assert len(history) == 3


def test_anti_clustering_queries(temp_db):
    """Verify anti-clustering check functions (already subbed, delivered today, subs last hour)."""
    channel = "@AntiClusterTest"
    order_id = create_order(
        channel_url=f"https://www.youtube.com/{channel}",
        target_subs=10,
        daily_cap=5,
        db_path=temp_db,
    )

    # Initial state
    assert has_account_subbed(201, channel, db_path=temp_db) is False
    assert get_delivered_today(order_id, db_path=temp_db) == 0
    assert get_subs_last_hour(channel, db_path=temp_db) == 0

    # Log successful sub for account 201
    log_sub_attempt(
        order_id=order_id,
        account_id=201,
        channel_id=channel,
        watch_seconds=100,
        sub_success=True,
        db_path=temp_db,
    )

    # Check updated state
    assert has_account_subbed(201, channel, db_path=temp_db) is True
    assert has_account_subbed(202, channel, db_path=temp_db) is False
    assert get_delivered_today(order_id, db_path=temp_db) == 1
    assert get_subs_last_hour(channel, db_path=temp_db) == 1


def test_order_stats_aggregation(temp_db):
    """Verify aggregated metrics calculation across all orders and attempts."""
    o1 = create_order("https://www.youtube.com/@Chan1", 5, db_path=temp_db)
    o2 = create_order("https://www.youtube.com/@Chan2", 10, db_path=temp_db)

    # Log 1 success on o1, 1 failure on o2
    log_sub_attempt(o1, 1, "@Chan1", watch_seconds=90, sub_success=True, db_path=temp_db)
    log_sub_attempt(o2, 2, "@Chan2", watch_seconds=30, sub_success=False, fail_reason="captcha", db_path=temp_db)

    stats = get_order_stats(db_path=temp_db)
    assert stats["total_orders"] == 2
    assert stats["active_orders"] == 2
    assert stats["total_delivered"] == 1
    assert stats["total_attempts"] == 2
    assert stats["success_attempts"] == 1
    assert stats["success_rate"] == 50.0
