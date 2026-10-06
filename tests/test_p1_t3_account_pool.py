# -*- coding: utf-8 -*-
"""
Unit test suite for Phase 1 Task 3 (P1.T3): Account Pool Bridge (account_pool.py).
Tests distributed locking, auto-expiry, tier priority, cooldowns, and pool metrics.
"""
import os
import sys
import sqlite3
import pytest

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from buff_sub.account_pool import (
    lock_account,
    release_lock,
    acquire_account_lock,
    LockAcquisitionError,
    get_ready_accounts,
    update_cooldown,
    is_available,
    get_account,
    get_pool_status,
)


@pytest.fixture
def temp_account_db(tmp_path):
    """Fixture creating an isolated shared account_pool.db with mock profiles and accounts."""
    db_file = str(tmp_path / "mock_account_pool.db")
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    # 1. gpm_profiles
    cursor.execute("""
    CREATE TABLE gpm_profiles (
        id              TEXT PRIMARY KEY,
        gmail           TEXT NOT NULL UNIQUE,
        proxy           TEXT,
        is_active       INTEGER DEFAULT 1,
        last_used_at    TEXT,
        notes           TEXT
    );
    """)

    # 2. sub_accounts
    cursor.execute("""
    CREATE TABLE sub_accounts (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        gpm_profile_id  TEXT NOT NULL,
        account_type    TEXT NOT NULL,
        channel_id      TEXT UNIQUE,
        channel_url     TEXT,
        switch_name     TEXT,
        niche           TEXT DEFAULT 'general',
        warmup_status   TEXT DEFAULT 'cold',
        warmup_days     INTEGER DEFAULT 0,
        warmup_videos   INTEGER DEFAULT 0,
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

    # 3. account_locks
    cursor.execute("""
    CREATE TABLE account_locks (
        account_id      INTEGER PRIMARY KEY,
        locked_by       TEXT NOT NULL,
        locked_at       TEXT DEFAULT (datetime('now')),
        expires_at      TEXT NOT NULL,
        FOREIGN KEY(account_id) REFERENCES sub_accounts(id)
    );
    """)

    # Seed 2 GPM Profiles
    cursor.execute("INSERT INTO gpm_profiles (id, gmail, proxy) VALUES ('prof-1', 'user1@gmail.com', 'proxy1:8080');")
    cursor.execute("INSERT INTO gpm_profiles (id, gmail, proxy) VALUES ('prof-2', 'user2@gmail.com', 'proxy2:8080');")

    # Seed Accounts for prof-1: 1 gmail_root, 1 brand_account
    cursor.execute("""
    INSERT INTO sub_accounts (id, gpm_profile_id, account_type, channel_id, switch_name, warmup_status, is_active)
    VALUES (1, 'prof-1', 'gmail_root', '@root_1', 'Root One', 'ready', 1);
    """)
    cursor.execute("""
    INSERT INTO sub_accounts (id, gpm_profile_id, account_type, channel_id, switch_name, warmup_status, is_active)
    VALUES (2, 'prof-1', 'brand_account', '@brand_1', 'Brand One', 'ready', 1);
    """)

    # Seed Accounts for prof-2: 1 gmail_root, 1 brand_account (cold)
    cursor.execute("""
    INSERT INTO sub_accounts (id, gpm_profile_id, account_type, channel_id, switch_name, warmup_status, is_active)
    VALUES (3, 'prof-2', 'gmail_root', '@root_2', 'Root Two', 'ready', 1);
    """)
    cursor.execute("""
    INSERT INTO sub_accounts (id, gpm_profile_id, account_type, channel_id, switch_name, warmup_status, is_active)
    VALUES (4, 'prof-2', 'brand_account', '@brand_2', 'Brand Two', 'cold', 1);
    """)

    conn.commit()
    conn.close()
    return db_file


def test_lock_and_release(temp_account_db):
    """Verify lock acquisition, collision prevention, and release."""
    account_id = 1

    # 1. First lock succeeds
    assert lock_account(account_id, locked_by="buff_sub", duration_min=10, db_path=temp_account_db) is True

    # 2. Duplicate lock attempt fails
    assert lock_account(account_id, locked_by="another_worker", duration_min=10, db_path=temp_account_db) is False

    # 3. Release lock
    assert release_lock(account_id, db_path=temp_account_db) is True

    # 4. Lock succeeds again after release
    assert lock_account(account_id, locked_by="another_worker", duration_min=10, db_path=temp_account_db) is True
    release_lock(account_id, db_path=temp_account_db)


def test_expired_lock_takeover(temp_account_db):
    """Verify that an expired lock is automatically purged and taken over."""
    account_id = 2
    conn = sqlite3.connect(temp_account_db)
    cursor = conn.cursor()
    # Insert an expired lock (expired 10 minutes ago)
    cursor.execute(
        """
        INSERT INTO account_locks (account_id, locked_by, locked_at, expires_at)
        VALUES (?, 'old_worker', datetime('now', '-20 minutes'), datetime('now', '-10 minutes'));
        """,
        (account_id,),
    )
    conn.commit()
    conn.close()

    # Lock attempt should purge the expired lock and succeed
    assert lock_account(account_id, locked_by="new_worker", duration_min=15, db_path=temp_account_db) is True
    release_lock(account_id, db_path=temp_account_db)


def test_acquire_account_lock_context_manager(temp_account_db):
    """Verify acquire_account_lock context manager handles clean release and exceptions."""
    account_id = 3

    # Normal block
    with acquire_account_lock(account_id, locked_by="test_run", db_path=temp_account_db):
        # Should be locked inside the block
        assert lock_account(account_id, locked_by="competing", db_path=temp_account_db) is False

    # Should be released outside the block
    assert lock_account(account_id, locked_by="competing", db_path=temp_account_db) is True
    release_lock(account_id, db_path=temp_account_db)

    # Exception block
    try:
        with acquire_account_lock(account_id, locked_by="crash_test", db_path=temp_account_db):
            raise RuntimeError("Simulated crash")
    except RuntimeError:
        pass

    # Should be cleanly released despite exception
    assert lock_account(account_id, locked_by="post_crash", db_path=temp_account_db) is True
    release_lock(account_id, db_path=temp_account_db)


def test_get_ready_accounts_tier_priority(temp_account_db):
    """
    Verify get_ready_accounts returns gmail_root before brand_account,
    and respects warmup_status ('cold' excluded).
    """
    ready = get_ready_accounts(limit=10, db_path=temp_account_db)
    assert len(ready) == 3  # Accounts 1 (root), 2 (brand), 3 (root) are ready; 4 is cold

    # First two must be gmail_root (Tier 1)
    assert ready[0]["account_type"] == "gmail_root"
    assert ready[1]["account_type"] == "gmail_root"
    # Third must be brand_account (Tier 2)
    assert ready[2]["account_type"] == "brand_account"

    # Test exclusion of GPM profile
    filtered = get_ready_accounts(limit=10, exclude_gpm_profile_ids=["prof-1"], db_path=temp_account_db)
    assert len(filtered) == 1
    assert filtered[0]["gpm_profile_id"] == "prof-2"


def test_cooldown_and_monthly_ceiling(temp_account_db):
    """Verify cooldown application and monthly ceiling enforcement."""
    account_id = 1

    assert is_available(account_id, db_path=temp_account_db) is True

    # Apply 3-day cooldown
    assert update_cooldown(account_id, days=3, db_path=temp_account_db) is True

    # Account is now on cooldown
    assert is_available(account_id, db_path=temp_account_db) is False
    ready_after = get_ready_accounts(limit=10, db_path=temp_account_db)
    assert all(a["id"] != account_id for a in ready_after)

    # Simulate reaching monthly limit on account 2
    conn = sqlite3.connect(temp_account_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE sub_accounts SET subs_this_month = 8 WHERE id = 2;")
    conn.commit()
    conn.close()

    assert is_available(2, db_path=temp_account_db) is False


def test_get_account_and_pool_status(temp_account_db):
    """Verify detailed account lookup and pool statistics calculation."""
    acc = get_account(1, db_path=temp_account_db)
    assert acc is not None
    assert acc["gmail"] == "user1@gmail.com"
    assert acc["proxy"] == "proxy1:8080"
    assert acc["account_type"] == "gmail_root"

    status = get_pool_status(db_path=temp_account_db)
    assert status["total_gpm_profiles"] == 2
    assert status["active_gpm_profiles"] == 2
    assert status["total_sub_accounts"] == 4
    assert status["ready_accounts"] == 3
    assert status["cold_accounts"] == 1
    assert status["available_now"] >= 2
