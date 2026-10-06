# -*- coding: utf-8 -*-
"""
account_pool.py — Shared Account Pool Bridge & Distributed Lock Manager
Interfaces with shared/account_pool.db, providing thread-safe locking,
priority-based account allocation, and cooldown lifecycle guardrails.
"""
import os
import sqlite3
import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from .config import (
    SHARED_DB_PATH,
    PROFILE_LOCK_TIMEOUT_MIN,
    COOLDOWN_DAYS_AFTER_SUB,
    MAX_SUBS_PER_ACCOUNT_MONTH,
)
from .logger import log


class LockAcquisitionError(Exception):
    """Raised when an account cannot be locked due to an active lock by another process."""
    pass


def get_shared_db_connection(db_path: str = SHARED_DB_PATH) -> sqlite3.Connection:
    """Open a connection to the shared account_pool.db with WAL mode and row factory."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Shared account database not found at: {db_path}")
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def lock_account(
    account_id: int,
    locked_by: str = "buff_sub",
    duration_min: int = PROFILE_LOCK_TIMEOUT_MIN,
    db_path: str = SHARED_DB_PATH,
) -> bool:
    """
    Atomically acquire an execution lock for an account.
    Automatically purges expired locks before attempting to acquire.
    Returns True if lock acquired, False if currently locked by another active process.
    """
    conn = get_shared_db_connection(db_path)
    cursor = conn.cursor()

    try:
        # 1. Clean up expired lock for this account if exists
        cursor.execute(
            "DELETE FROM account_locks WHERE account_id = ? AND expires_at <= datetime('now');",
            (account_id,),
        )

        # 2. Try to insert new lock
        cursor.execute(
            """
            INSERT INTO account_locks (account_id, locked_by, locked_at, expires_at)
            VALUES (?, ?, datetime('now'), datetime('now', '+' || ? || ' minutes'));
            """,
            (account_id, locked_by, duration_min),
        )
        conn.commit()
        log(f"Acquired lock on Account #{account_id} for {duration_min}m by '{locked_by}'", "INFO")
        return True
    except sqlite3.IntegrityError:
        # Lock exists and has not expired
        log(f"Account #{account_id} is currently locked by another process.", "WARN")
        return False
    finally:
        conn.close()


def release_lock(
    account_id: int,
    locked_by: Optional[str] = None,
    db_path: str = SHARED_DB_PATH,
) -> bool:
    """
    Release a held lock for an account.
    If locked_by is provided, only deletes if the lock matches the owner.
    """
    conn = get_shared_db_connection(db_path)
    cursor = conn.cursor()

    if locked_by:
        cursor.execute(
            "DELETE FROM account_locks WHERE account_id = ? AND locked_by = ?;",
            (account_id, locked_by),
        )
    else:
        cursor.execute(
            "DELETE FROM account_locks WHERE account_id = ?;",
            (account_id,),
        )

    released = cursor.rowcount > 0
    conn.commit()
    conn.close()

    if released:
        log(f"Released lock on Account #{account_id}", "INFO")
    return released


@contextmanager
def acquire_account_lock(
    account_id: int,
    locked_by: str = "buff_sub",
    duration_min: int = PROFILE_LOCK_TIMEOUT_MIN,
    db_path: str = SHARED_DB_PATH,
):
    """
    Context manager to safely lock and automatically release an account.
    Raises LockAcquisitionError if lock cannot be acquired.
    """
    if not lock_account(account_id, locked_by=locked_by, duration_min=duration_min, db_path=db_path):
        raise LockAcquisitionError(f"Could not acquire lock for Account #{account_id}")
    try:
        yield
    finally:
        release_lock(account_id, locked_by=locked_by, db_path=db_path)


def get_ready_accounts(
    limit: int = 10,
    exclude_gpm_profile_ids: Optional[List[str]] = None,
    db_path: str = SHARED_DB_PATH,
) -> List[Dict[str, Any]]:
    """
    Query accounts eligible to execute subscription sessions.
    Criteria:
      - sub_accounts.warmup_status = 'ready'
      - sub_accounts.is_active = 1
      - gpm_profiles.is_active = 1
      - cooldown_until IS NULL OR cooldown_until <= datetime('now')
      - subs_this_month < MAX_SUBS_PER_ACCOUNT_MONTH (default 8)
      - Not currently locked (account_id not in active account_locks)
      - Not in exclude_gpm_profile_ids (used for anti-clustering diversity)
    Sorting:
      - Priority Tier 1: gmail_root first, then brand_account
      - Idle duration: last_sub_at ASC NULLS FIRST (account with longest rest first)
    """
    conn = get_shared_db_connection(db_path)
    cursor = conn.cursor()

    query = """
    SELECT
        sa.*,
        gp.gmail,
        gp.proxy,
        gp.notes AS gpm_notes
    FROM sub_accounts sa
    JOIN gpm_profiles gp ON sa.gpm_profile_id = gp.id
    WHERE sa.warmup_status = 'ready'
      AND sa.is_active = 1
      AND gp.is_active = 1
      AND (sa.cooldown_until IS NULL OR sa.cooldown_until <= datetime('now'))
      AND (sa.subs_this_month < ?)
      AND sa.id NOT IN (
          SELECT account_id FROM account_locks WHERE expires_at > datetime('now')
      )
    """
    params: List[Any] = [MAX_SUBS_PER_ACCOUNT_MONTH]

    if exclude_gpm_profile_ids:
        placeholders = ",".join(["?"] * len(exclude_gpm_profile_ids))
        query += f" AND sa.gpm_profile_id NOT IN ({placeholders})"
        params.extend(exclude_gpm_profile_ids)

    query += """
    ORDER BY
        (CASE WHEN sa.account_type = 'gmail_root' THEN 1 ELSE 2 END) ASC,
        (CASE WHEN sa.last_sub_at IS NULL THEN 0 ELSE 1 END) ASC,
        sa.last_sub_at ASC,
        sa.id ASC
    LIMIT ?;
    """
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_cooldown(
    account_id: int,
    days: int = COOLDOWN_DAYS_AFTER_SUB,
    db_path: str = SHARED_DB_PATH,
) -> bool:
    """
    Update post-subscription cooldown and increment usage counters for an account.
    Sets cooldown_until = now() + days, last_sub_at = now(),
    increments total_subs_done and subs_this_month.
    """
    conn = get_shared_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE sub_accounts
        SET cooldown_until = datetime('now', '+' || ? || ' days'),
            last_sub_at = datetime('now'),
            total_subs_done = COALESCE(total_subs_done, 0) + 1,
            subs_this_month = COALESCE(subs_this_month, 0) + 1
        WHERE id = ?;
        """,
        (days, account_id),
    )
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()

    if updated:
        log(f"Updated Account #{account_id} cooldown (+{days} days, incremented sub counters)", "SUCCESS")
    return updated


def is_available(account_id: int, db_path: str = SHARED_DB_PATH) -> bool:
    """
    Check if a specific account is currently available for work:
    active, ready, not on cooldown, under monthly limit, and not locked.
    """
    conn = get_shared_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT 1
        FROM sub_accounts sa
        JOIN gpm_profiles gp ON sa.gpm_profile_id = gp.id
        WHERE sa.id = ?
          AND sa.warmup_status = 'ready'
          AND sa.is_active = 1
          AND gp.is_active = 1
          AND (sa.cooldown_until IS NULL OR sa.cooldown_until <= datetime('now'))
          AND (sa.subs_this_month < ?)
          AND sa.id NOT IN (
              SELECT account_id FROM account_locks WHERE expires_at > datetime('now')
          )
        LIMIT 1;
        """,
        (account_id, MAX_SUBS_PER_ACCOUNT_MONTH),
    )
    result = cursor.fetchone() is not None
    conn.close()
    return result


def get_account(account_id: int, db_path: str = SHARED_DB_PATH) -> Optional[Dict[str, Any]]:
    """Retrieve full account row joined with GPM profile details."""
    conn = get_shared_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            sa.*,
            gp.gmail,
            gp.proxy,
            gp.notes AS gpm_notes
        FROM sub_accounts sa
        JOIN gpm_profiles gp ON sa.gpm_profile_id = gp.id
        WHERE sa.id = ?;
        """,
        (account_id,),
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_pool_status(db_path: str = SHARED_DB_PATH) -> Dict[str, Any]:
    """
    Aggregate summary metrics across GPM profiles and sub accounts.
    Returns status counts, active locks, cooldowns, and immediately available slots.
    """
    conn = get_shared_db_connection(db_path)
    cursor = conn.cursor()

    total_profiles = cursor.execute("SELECT COUNT(*) FROM gpm_profiles;").fetchone()[0]
    active_profiles = cursor.execute("SELECT COUNT(*) FROM gpm_profiles WHERE is_active = 1;").fetchone()[0]

    total_accounts = cursor.execute("SELECT COUNT(*) FROM sub_accounts;").fetchone()[0]
    gmail_root_accounts = cursor.execute("SELECT COUNT(*) FROM sub_accounts WHERE account_type = 'gmail_root';").fetchone()[0]
    brand_accounts = cursor.execute("SELECT COUNT(*) FROM sub_accounts WHERE account_type = 'brand_account';").fetchone()[0]

    ready_accounts = cursor.execute("SELECT COUNT(*) FROM sub_accounts WHERE warmup_status = 'ready';").fetchone()[0]
    warming_accounts = cursor.execute("SELECT COUNT(*) FROM sub_accounts WHERE warmup_status = 'warming';").fetchone()[0]
    cold_accounts = cursor.execute("SELECT COUNT(*) FROM sub_accounts WHERE warmup_status = 'cold';").fetchone()[0]
    suspended_accounts = cursor.execute("SELECT COUNT(*) FROM sub_accounts WHERE warmup_status = 'suspended';").fetchone()[0]

    active_locks = cursor.execute(
        "SELECT COUNT(*) FROM account_locks WHERE expires_at > datetime('now');"
    ).fetchone()[0]

    on_cooldown = cursor.execute(
        "SELECT COUNT(*) FROM sub_accounts WHERE cooldown_until > datetime('now');"
    ).fetchone()[0]

    # Available now (ready + active + cooldown passed + not locked + under monthly limit)
    available_now = cursor.execute(
        """
        SELECT COUNT(*)
        FROM sub_accounts sa
        JOIN gpm_profiles gp ON sa.gpm_profile_id = gp.id
        WHERE sa.warmup_status = 'ready'
          AND sa.is_active = 1
          AND gp.is_active = 1
          AND (sa.cooldown_until IS NULL OR sa.cooldown_until <= datetime('now'))
          AND (sa.subs_this_month < ?)
          AND sa.id NOT IN (
              SELECT account_id FROM account_locks WHERE expires_at > datetime('now')
          );
        """,
        (MAX_SUBS_PER_ACCOUNT_MONTH,),
    ).fetchone()[0]

    conn.close()

    return {
        "total_gpm_profiles": total_profiles,
        "active_gpm_profiles": active_profiles,
        "total_sub_accounts": total_accounts,
        "gmail_root_accounts": gmail_root_accounts,
        "brand_accounts": brand_accounts,
        "ready_accounts": ready_accounts,
        "warming_accounts": warming_accounts,
        "cold_accounts": cold_accounts,
        "suspended_accounts": suspended_accounts,
        "active_locks": active_locks,
        "on_cooldown": on_cooldown,
        "available_now": available_now,
    }


def list_sub_accounts(
    limit: int = 100,
    offset: int = 0,
    tier: Optional[str] = None,
    warmup_status: Optional[str] = None,
    db_path: str = SHARED_DB_PATH,
) -> Dict[str, Any]:
    """
    List sub accounts with pagination, filter, and lock/cooldown flags.
    Returns: {"total": int, "accounts": List[Dict[str, Any]]}
    """
    conn = get_shared_db_connection(db_path)
    cursor = conn.cursor()

    conditions = []
    params: list = []

    if tier:
        conditions.append("sa.account_type = ?")
        params.append(tier)
    if warmup_status:
        conditions.append("sa.warmup_status = ?")
        params.append(warmup_status)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # Total count
    count_sql = f"SELECT COUNT(*) FROM sub_accounts sa {where_clause};"
    total = cursor.execute(count_sql, params).fetchone()[0]

    # Query with join on locks and gpm_profiles
    query_sql = f"""
    SELECT
        sa.id,
        sa.gpm_profile_id,
        gp.gmail as gpm_profile_name,
        sa.account_type,
        sa.channel_id,
        sa.switch_name as channel_name,
        sa.warmup_status,
        sa.cooldown_until,
        sa.subs_this_month,
        sa.last_sub_at,
        CASE WHEN al.account_id IS NOT NULL THEN 1 ELSE 0 END as is_locked,
        al.locked_by,
        al.expires_at as lock_expires_at,
        CASE WHEN sa.cooldown_until > datetime('now') THEN 1 ELSE 0 END as is_on_cooldown
    FROM sub_accounts sa
    LEFT JOIN gpm_profiles gp ON sa.gpm_profile_id = gp.id
    LEFT JOIN account_locks al ON sa.id = al.account_id AND al.expires_at > datetime('now')
    {where_clause}
    ORDER BY sa.id ASC
    LIMIT ? OFFSET ?;
    """
    query_params = params + [limit, offset]
    cursor.execute(query_sql, query_params)
    rows = cursor.fetchall()
    conn.close()

    return {
        "total": total,
        "accounts": [dict(r) for r in rows],
    }


def sync_gpm_profiles_to_pool(db_path: str = SHARED_DB_PATH) -> int:
    """
    Query GPM Login API and sync profiles matching strictly 'sub_yt-x' (x is integer).
    Purges any profile from shared pool that does not conform to this naming convention.
    """
    import re
    import requests
    from .config import GPM_API_URL, REQUIRED_PROFILE_REGEX

    try:
        resp = requests.get(f"{GPM_API_URL}/v2/profiles?page=1&per_page=200", timeout=5)
        if resp.status_code != 200:
            log(f"GPM API returned status {resp.status_code} during profile sync", "WARN")
            return 0
        data = resp.json()
        raw_profiles = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    except Exception as e:
        log(f"Could not connect to GPM API for profile sync: {e}", "WARN")
        return 0

    valid_profiles = []
    for p in raw_profiles:
        name = str(p.get("name", "")).strip()
        if re.match(REQUIRED_PROFILE_REGEX, name):
            valid_profiles.append(p)

    conn = get_shared_db_connection(db_path)
    cur = conn.cursor()
    synced_count = 0

    try:
        valid_ids = [str(p.get("id") or p.get("profile_id", "")).strip() for p in valid_profiles if (p.get("id") or p.get("profile_id"))]

        # Delete sub_accounts and gpm_profiles not matching sub_yt-x
        if valid_ids:
            placeholders = ",".join("?" for _ in valid_ids)
            cur.execute(f"DELETE FROM account_locks WHERE account_id IN (SELECT id FROM sub_accounts WHERE gpm_profile_id NOT IN ({placeholders}));", valid_ids)
            cur.execute(f"DELETE FROM sub_accounts WHERE gpm_profile_id NOT IN ({placeholders});", valid_ids)
            cur.execute(f"DELETE FROM gpm_profiles WHERE id NOT IN ({placeholders});", valid_ids)
        else:
            cur.execute("DELETE FROM account_locks;")
            cur.execute("DELETE FROM sub_accounts;")
            cur.execute("DELETE FROM gpm_profiles;")

        # Upsert matching valid profiles
        now_str = datetime.datetime.now().isoformat()
        for p in valid_profiles:
            p_id = str(p.get("id") or p.get("profile_id", "")).strip()
            name = str(p.get("name", "")).strip()
            proxy = str(p.get("proxy", "")).strip()
            gmail = p.get("email") or p.get("gmail") or (name if "@" in name else f"{name}@gmail.local")

            cur.execute(
                """
                INSERT INTO gpm_profiles (id, gmail, proxy, is_active, last_used_at, notes)
                VALUES (?, ?, ?, 1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    proxy = excluded.proxy,
                    notes = excluded.notes;
                """,
                (p_id, gmail, proxy, now_str, f"Discovered: {name}"),
            )

            # Ensure root account exists for this profile
            cur.execute(
                """
                INSERT INTO sub_accounts (
                    gpm_profile_id, account_type, channel_id, switch_name,
                    warmup_status, warmup_days, warmup_videos, is_active, created_at
                )
                VALUES (?, 'gmail_root', ?, ?, 'ready', 30, 50, 1, ?)
                ON CONFLICT(channel_id) DO NOTHING;
                """,
                (p_id, f"root_{p_id}", name, now_str),
            )
            synced_count += 1

        conn.commit()
        if synced_count > 0:
            log(f"Successfully synced {synced_count} matching 'sub_yt-x' profiles to shared pool.", "SUCCESS")
        else:
            log("No profiles matching 'sub_yt-x' found in GPM. Account pool is in STANDBY mode (0 profiles).", "WARN")
        return synced_count
    finally:
        conn.close()


