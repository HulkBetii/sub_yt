# -*- coding: utf-8 -*-
"""
health_monitor.py — Production Account Health Monitor & Cluster Protection
Detects Google flags, CAPTCHAs, SMS challenges, and action blocks.
Provides automatic account isolation (auto-suspend) and cluster leak protection.
"""
import os
import sqlite3
import datetime
from typing import Tuple, Optional, Dict, Any, List

from .config import SHARED_DB_PATH
from .logger import log
from .account_pool import get_shared_db_connection, release_lock


# ── Error Severity Categories ─────────────────────────────────────
HEALTHY = "HEALTHY"
TRANSIENT_ERROR = "TRANSIENT_ERROR"
SESSION_EXPIRED = "SESSION_EXPIRED"
PHONE_VERIFY_REQUIRED = "PHONE_VERIFY_REQUIRED"
ACTION_BLOCKED = "ACTION_BLOCKED"
BOT_CAPTCHA = "BOT_CAPTCHA"

FATAL_CONDITIONS = {
    SESSION_EXPIRED,
    PHONE_VERIFY_REQUIRED,
    ACTION_BLOCKED,
    BOT_CAPTCHA,
}

DEFAULT_CLUSTER_SUSPEND_THRESHOLD = 0.20  # >= 20% accounts suspended triggers profile shutdown


# ── Browser Inspection & Diagnostic ──────────────────────────────

def analyze_driver_health(driver: Any) -> Tuple[str, Optional[str]]:
    """
    Examine the active Selenium driver to diagnose account health.
    Returns: (status_code, diagnostic_reason)
    """
    if driver is None:
        return TRANSIENT_ERROR, "Driver is not available"

    try:
        cur_url = ""
        try:
            cur_url = (driver.current_url or "").lower()
        except Exception:
            return TRANSIENT_ERROR, "Could not fetch current URL (browser may be unresponsive)"

        # 1. Check for Login / Session Expiration
        if any(kw in cur_url for kw in ("accounts.google.com/signin", "accounts.google.com/v3/signin", "accounts.google.com/servicelogin")):
            return SESSION_EXPIRED, f"Redirected to Google sign-in: {cur_url[:60]}"

        # 2. Check for Phone Verification / IDV challenge
        if any(kw in cur_url for kw in ("idv", "idvpreregistered", "challenge/pwd", "speedbump/idv")):
            return PHONE_VERIFY_REQUIRED, f"Redirected to Google IDV challenge: {cur_url[:60]}"

        # Inspect page source
        page_source = ""
        try:
            page_source = (driver.page_source or "").lower()
        except Exception:
            return HEALTHY, None

        # Phone verify text patterns
        phone_patterns = [
            "verify your account",
            "xác minh tài khoản của bạn",
            "enter a phone number",
            "nhập số điện thoại",
            "text message (sms)",
            "verify it's you",
            "xác minh danh tính",
        ]
        for pat in phone_patterns:
            if pat in page_source:
                return PHONE_VERIFY_REQUIRED, f"Page prompt requires verification: '{pat}'"

        # Action blocked / Restriction patterns
        action_block_patterns = [
            "this action is not allowed",
            "hành động này không được phép",
            "action blocked",
            "please try again later",
            "vui lòng thử lại sau",
            "your account is restricted",
        ]
        for pat in action_block_patterns:
            if pat in page_source:
                return ACTION_BLOCKED, f"YouTube restricted action: '{pat}'"

        # CAPTCHA / Unusual traffic patterns
        captcha_patterns = [
            "unusual traffic from your computer network",
            "lưu lượng bất thường từ mạng máy tính",
            "our systems have detected unusual traffic",
            "recaptcha",
            "hcaptcha",
        ]
        for pat in captcha_patterns:
            if pat in page_source:
                return BOT_CAPTCHA, f"Bot protection triggered: '{pat}'"

        return HEALTHY, None

    except Exception as e:
        log(f"Error during driver health analysis: {e}", "WARN")
        return TRANSIENT_ERROR, f"Health check exception: {str(e)[:60]}"


# ── Account Isolation (Auto-Suspend) ──────────────────────────────

def suspend_account(
    account_id: int,
    reason: str,
    db_path: str = SHARED_DB_PATH,
) -> bool:
    """
    Safely isolate a damaged account:
    1. Sets warmup_status = 'suspended' in sub_accounts.
    2. Logs reason and releases any held lock.
    """
    log(f"🚨 AUTO-SUSPENDING Account #{account_id} | Reason: {reason}", "WARN")

    conn = get_shared_db_connection(db_path)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE sub_accounts
            SET warmup_status = 'suspended'
            WHERE id = ?;
            """,
            (account_id,),
        )
        conn.commit()
    finally:
        conn.close()

    # Always release lock so worker processes do not stall
    release_lock(account_id, db_path=db_path)
    return True


# ── Cluster Leak Protection ───────────────────────────────────────

def check_cluster_health_and_protect(
    gpm_profile_id: str,
    threshold_ratio: float = DEFAULT_CLUSTER_SUSPEND_THRESHOLD,
    db_path: str = SHARED_DB_PATH,
) -> bool:
    """
    Audit all accounts associated with the specified Master GPM Profile.
    If >= threshold_ratio of accounts are suspended, automatically deactivates
    the entire GPM profile to prevent cluster infection and IP/proxy blacklisting.
    Returns True if profile was deactivated, False otherwise.
    """
    conn = get_shared_db_connection(db_path)
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT COUNT(*) FROM sub_accounts WHERE gpm_profile_id = ?;",
            (gpm_profile_id,),
        )
        total_accounts = cur.fetchone()[0]

        if total_accounts == 0:
            return False

        cur.execute(
            "SELECT COUNT(*) FROM sub_accounts WHERE gpm_profile_id = ? AND warmup_status = 'suspended';",
            (gpm_profile_id,),
        )
        suspended_accounts = cur.fetchone()[0]

        suspension_ratio = suspended_accounts / float(total_accounts)

        # Trigger protection if threshold met and at least 1 account is suspended
        if suspended_accounts >= 1 and suspension_ratio >= threshold_ratio:
            note_append = f" [AUTO-DEACTIVATED: Cluster leak detected ({suspended_accounts}/{total_accounts} accounts suspended)]"
            cur.execute(
                """
                UPDATE gpm_profiles
                SET is_active = 0,
                    notes = COALESCE(notes, '') || ?
                WHERE id = ?;
                """,
                (note_append, gpm_profile_id),
            )
            conn.commit()
            log(
                f"🛑 CLUSTER PROTECTION TRIGGERED! Deactivated GPM Profile '{gpm_profile_id}' "
                f"({suspended_accounts}/{total_accounts} = {suspension_ratio:.1%} suspended >= {threshold_ratio:.1%}).",
                "ERROR",
            )
            return True

        return False
    finally:
        conn.close()
