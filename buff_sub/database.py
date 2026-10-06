# -*- coding: utf-8 -*-
"""
database.py — Internal SQLite Database Layer for buff-sub-yt Engine
Manages subscription orders, execution history, and anti-clustering guardrail metrics.
"""
import os
import re
import sqlite3
import datetime
from typing import Optional, List, Dict, Any

from .config import LOCAL_DB_PATH
from .logger import log


def extract_channel_id(channel_url: str) -> str:
    """
    Extract channel handle or channel ID from YouTube URL.
    Examples:
        https://www.youtube.com/@ChannelName -> @ChannelName
        https://www.youtube.com/channel/UC12345 -> UC12345
        @ChannelName -> @ChannelName
    """
    if not channel_url:
        return ""
    clean = channel_url.strip()
    # Match @handle
    handle_match = re.search(r"(@[\w\.-]+)", clean)
    if handle_match:
        return handle_match.group(1)
    # Match /channel/UCxxx
    uc_match = re.search(r"/channel/(UC[\w-]+)", clean)
    if uc_match:
        return uc_match.group(1)
    # Match /c/name or /user/name
    c_match = re.search(r"/(?:c|user)/([\w\.-]+)", clean)
    if c_match:
        return c_match.group(1)
    # Fallback to last segment
    segments = [s for s in clean.split("/") if s]
    return segments[-1] if segments else clean


def get_db_connection(db_path: str = LOCAL_DB_PATH) -> sqlite3.Connection:
    """Create a SQLite connection configured with WAL mode and row factory."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db(db_path: str = LOCAL_DB_PATH) -> None:
    """Initialize orders and sub_history tables with proper indexes."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # 1. Orders table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_url     TEXT NOT NULL,
        channel_id      TEXT,
        target_subs     INTEGER NOT NULL,
        delivered       INTEGER DEFAULT 0,
        status          TEXT DEFAULT 'pending',  -- 'pending', 'running', 'paused', 'completed', 'failed'
        daily_cap       INTEGER DEFAULT 20,
        priority        INTEGER DEFAULT 5,
        customer_note   TEXT,
        created_at      TEXT DEFAULT (datetime('now')),
        completed_at    TEXT
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);")

    # 2. Sub History table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sub_history (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id        INTEGER NOT NULL,
        account_id      INTEGER NOT NULL,
        channel_id      TEXT NOT NULL,
        watch_seconds   INTEGER DEFAULT 0,
        did_like        INTEGER DEFAULT 0,
        sub_success     INTEGER DEFAULT 0,
        fail_reason     TEXT,
        executed_at     TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sub_history_order ON sub_history(order_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sub_history_account ON sub_history(account_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sub_history_channel ON sub_history(channel_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sub_history_executed ON sub_history(executed_at);")

    conn.commit()
    conn.close()
    log(f"Local database initialized at: {db_path}", "INFO")


def create_order(
    channel_url: str,
    target_subs: int,
    daily_cap: int = 20,
    priority: int = 5,
    channel_id: Optional[str] = None,
    customer_note: Optional[str] = None,
    db_path: str = LOCAL_DB_PATH,
) -> int:
    """Create a new subscription order and return its ID."""
    init_db(db_path)
    extracted_id = channel_id or extract_channel_id(channel_url)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO orders (channel_url, channel_id, target_subs, daily_cap, priority, customer_note, status)
        VALUES (?, ?, ?, ?, ?, ?, 'pending');
        """,
        (channel_url, extracted_id, target_subs, daily_cap, priority, customer_note),
    )
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()
    log(f"Created order #{order_id} for channel {extracted_id} (Target: {target_subs}, Daily cap: {daily_cap})", "SUCCESS")
    return order_id


def get_order(order_id: int, db_path: str = LOCAL_DB_PATH) -> Optional[Dict[str, Any]]:
    """Retrieve an order by ID as a dictionary."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id = ?;", (order_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def list_orders(status: Optional[str] = None, db_path: str = LOCAL_DB_PATH) -> List[Dict[str, Any]]:
    """List orders, optionally filtered by status, ordered by priority ASC, created_at DESC."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    if status:
        cursor.execute(
            "SELECT * FROM orders WHERE status = ? ORDER BY priority ASC, created_at DESC;",
            (status,),
        )
    else:
        cursor.execute("SELECT * FROM orders ORDER BY priority ASC, created_at DESC;")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_order_status(
    order_id: int,
    status: str,
    delivered: Optional[int] = None,
    db_path: str = LOCAL_DB_PATH,
) -> bool:
    """Update order status and optionally delivered count."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if status == "completed":
        if delivered is not None:
            cursor.execute(
                "UPDATE orders SET status = ?, delivered = ?, completed_at = ? WHERE id = ?;",
                (status, delivered, now_str, order_id),
            )
        else:
            cursor.execute(
                "UPDATE orders SET status = ?, completed_at = ? WHERE id = ?;",
                (status, now_str, order_id),
            )
    else:
        if delivered is not None:
            cursor.execute(
                "UPDATE orders SET status = ?, delivered = ? WHERE id = ?;",
                (status, delivered, order_id),
            )
        else:
            cursor.execute("UPDATE orders SET status = ? WHERE id = ?;", (status, order_id))

    changed = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def increment_order_delivered(order_id: int, db_path: str = LOCAL_DB_PATH) -> int:
    """
    Atomically increment delivered count for an order.
    Automatically marks order as 'completed' if delivered >= target_subs.
    Returns the new delivered count.
    """
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT target_subs, delivered FROM orders WHERE id = ?;", (order_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return 0

    target = row["target_subs"]
    new_delivered = (row["delivered"] or 0) + 1
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if new_delivered >= target:
        cursor.execute(
            "UPDATE orders SET delivered = ?, status = 'completed', completed_at = ? WHERE id = ?;",
            (new_delivered, now_str, order_id),
        )
        log(f"Order #{order_id} reached target {target}/{target}. Marked as COMPLETED.", "SUCCESS")
    else:
        cursor.execute(
            "UPDATE orders SET delivered = ?, status = 'running' WHERE id = ?;",
            (new_delivered, order_id),
        )

    conn.commit()
    conn.close()
    return new_delivered


def log_sub_attempt(
    order_id: int,
    account_id: int,
    channel_id: str,
    watch_seconds: int = 0,
    did_like: bool = False,
    sub_success: bool = False,
    fail_reason: Optional[str] = None,
    db_path: str = LOCAL_DB_PATH,
) -> int:
    """
    Record an execution attempt in sub_history.
    If sub_success is True, automatically increments the order delivered count.
    """
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO sub_history (order_id, account_id, channel_id, watch_seconds, did_like, sub_success, fail_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """,
        (
            order_id,
            account_id,
            channel_id,
            watch_seconds,
            1 if did_like else 0,
            1 if sub_success else 0,
            fail_reason,
        ),
    )
    history_id = cursor.lastrowid
    conn.commit()
    conn.close()

    if sub_success:
        increment_order_delivered(order_id, db_path=db_path)
        log(f"Logged successful sub for Order #{order_id} by Account #{account_id} (Watch: {watch_seconds}s)", "SUCCESS")
    else:
        log(f"Logged failed sub attempt for Order #{order_id} by Account #{account_id}. Reason: {fail_reason}", "WARN")

    return history_id


def get_sub_history(
    order_id: Optional[int] = None,
    limit: int = 50,
    db_path: str = LOCAL_DB_PATH,
) -> List[Dict[str, Any]]:
    """Retrieve execution history, optionally filtered by order_id, sorted latest first."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    if order_id is not None:
        cursor.execute(
            "SELECT * FROM sub_history WHERE order_id = ? ORDER BY executed_at DESC LIMIT ?;",
            (order_id, limit),
        )
    else:
        cursor.execute(
            "SELECT * FROM sub_history ORDER BY executed_at DESC LIMIT ?;",
            (limit,),
        )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def has_account_subbed(
    account_id: int,
    channel_id: str,
    db_path: str = LOCAL_DB_PATH,
) -> bool:
    """Check if a specific account has already successfully subscribed to this channel."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 1 FROM sub_history
        WHERE account_id = ? AND channel_id = ? AND sub_success = 1
        LIMIT 1;
        """,
        (account_id, channel_id),
    )
    result = cursor.fetchone() is not None
    conn.close()
    return result


def get_delivered_today(order_id: int, db_path: str = LOCAL_DB_PATH) -> int:
    """Return count of successful subscriptions delivered today for an order."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT COUNT(*) FROM sub_history
        WHERE order_id = ? AND sub_success = 1 AND executed_at >= datetime('now', 'start of day');
        """,
        (order_id,),
    )
    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_subs_last_hour(channel_id: str, db_path: str = LOCAL_DB_PATH) -> int:
    """
    Return count of subscription attempts made to this channel within the last 60 minutes.
    Used by anti-clustering guardrails (threshold: max 2-3 per hour).
    """
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT COUNT(*) FROM sub_history
        WHERE channel_id = ? AND sub_success = 1 AND executed_at >= datetime('now', '-1 hour');
        """,
        (channel_id,),
    )
    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_order_stats(db_path: str = LOCAL_DB_PATH) -> Dict[str, Any]:
    """Return summary statistics across all orders and execution history."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    total_orders = cursor.execute("SELECT COUNT(*) FROM orders;").fetchone()[0]
    active_orders = cursor.execute("SELECT COUNT(*) FROM orders WHERE status IN ('pending', 'running');").fetchone()[0]
    completed_orders = cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'completed';").fetchone()[0]
    total_delivered = cursor.execute("SELECT COALESCE(SUM(delivered), 0) FROM orders;").fetchone()[0]

    total_attempts = cursor.execute("SELECT COUNT(*) FROM sub_history;").fetchone()[0]
    success_attempts = cursor.execute("SELECT COUNT(*) FROM sub_history WHERE sub_success = 1;").fetchone()[0]

    success_rate = (success_attempts / total_attempts * 100) if total_attempts > 0 else 0.0

    conn.close()
    return {
        "total_orders": total_orders,
        "active_orders": active_orders,
        "completed_orders": completed_orders,
        "total_delivered": total_delivered,
        "total_attempts": total_attempts,
        "success_attempts": success_attempts,
        "success_rate": round(success_rate, 2),
    }


def delete_order(order_id: int, db_path: str = LOCAL_DB_PATH) -> bool:
    """Delete an order by ID (sub_history records deleted explicitly)."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sub_history WHERE order_id = ?;", (order_id,))
    cursor.execute("DELETE FROM orders WHERE id = ?;", (order_id,))
    changed = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def pause_order(order_id: int, db_path: str = LOCAL_DB_PATH) -> bool:
    """Pause an active or running order."""
    return update_order_status(order_id, status="paused", db_path=db_path)


def resume_order(order_id: int, db_path: str = LOCAL_DB_PATH) -> bool:
    """Resume a paused order back to running status."""
    return update_order_status(order_id, status="running", db_path=db_path)


def get_system_stats(db_path: str = LOCAL_DB_PATH) -> Dict[str, Any]:
    """Return consolidated system stats including orders and shared pool status."""
    order_stats = get_order_stats(db_path)
    pool_stats = {}
    try:
        from .account_pool import get_pool_status
        pool_stats = get_pool_status()
    except Exception:
        pass

    return {
        "orders": order_stats,
        "pool": pool_stats,
    }


def get_order_history(
    order_id: int,
    limit: int = 100,
    db_path: str = LOCAL_DB_PATH,
) -> List[Dict[str, Any]]:
    """Retrieve detailed execution attempts from sub_history for an order."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, order_id, account_id, channel_id, watch_seconds, did_like, sub_success, fail_reason, executed_at
        FROM sub_history
        WHERE order_id = ?
        ORDER BY id DESC
        LIMIT ?;
        """,
        (order_id, limit),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_order_export_data(
    order_id: int,
    db_path: str = LOCAL_DB_PATH,
) -> List[Dict[str, Any]]:
    """Retrieve full sub_history dataset suitable for CSV export."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            sh.id AS history_id,
            sh.executed_at,
            sh.account_id,
            sh.channel_id,
            sh.sub_success,
            sh.watch_seconds,
            sh.did_like,
            sh.fail_reason
        FROM sub_history sh
        WHERE sh.order_id = ?
        ORDER BY sh.id ASC;
        """,
        (order_id,),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_order_summary(
    order_id: int,
    db_path: str = LOCAL_DB_PATH,
) -> Optional[Dict[str, Any]]:
    """Generate comprehensive performance analytics for a single order."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM orders WHERE id = ?;", (order_id,))
    order_row = cursor.fetchone()
    if not order_row:
        conn.close()
        return None

    order_dict = dict(order_row)

    # Aggregate metrics from sub_history
    cursor.execute(
        """
        SELECT
            COUNT(*) AS total_attempts,
            COALESCE(SUM(CASE WHEN sub_success = 1 THEN 1 ELSE 0 END), 0) AS successful_subs,
            COALESCE(SUM(CASE WHEN sub_success = 0 THEN 1 ELSE 0 END), 0) AS failed_attempts,
            COALESCE(AVG(watch_seconds), 0) AS avg_watch_seconds,
            COALESCE(SUM(CASE WHEN did_like = 1 THEN 1 ELSE 0 END), 0) AS total_likes,
            COUNT(DISTINCT account_id) AS unique_accounts_count
        FROM sub_history
        WHERE order_id = ?;
        """,
        (order_id,),
    )
    agg = dict(cursor.fetchone())
    conn.close()

    total_att = agg["total_attempts"]
    succ = agg["successful_subs"]
    success_rate = (succ / float(total_att) * 100.0) if total_att > 0 else 0.0

    return {
        "order_id": order_dict["id"],
        "channel_url": order_dict["channel_url"],
        "channel_id": order_dict["channel_id"],
        "status": order_dict["status"],
        "target_subs": order_dict["target_subs"],
        "delivered": order_dict["delivered"],
        "daily_cap": order_dict["daily_cap"],
        "created_at": order_dict["created_at"],
        "completed_at": order_dict["completed_at"],
        "total_attempts": total_att,
        "successful_subs": succ,
        "failed_attempts": agg["failed_attempts"],
        "success_rate_percent": round(success_rate, 2),
        "avg_watch_seconds": round(float(agg["avg_watch_seconds"]), 1),
        "total_likes": agg["total_likes"],
        "unique_accounts_count": agg["unique_accounts_count"],
    }


