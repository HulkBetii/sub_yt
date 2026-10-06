# -*- coding: utf-8 -*-
"""
scheduler.py — Autonomous Drip-Feed Routine Scheduler for buff-sub-yt
Coordinates regular 15-30m routine ticks using APScheduler, enforces S-Curve growth,
hourly velocity guardrails, and master account diversity.
"""
import threading
import datetime
from typing import Optional, Dict, Any, List

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

import re
import sqlite3
import sys

from .logger import log
from .config import (
    SCHEDULER_TICK_INTERVAL_MINUTES,
    MAX_SUBS_PER_CHANNEL_PER_HOUR,
    LOCAL_DB_PATH,
    SHARED_DB_PATH,
    CIRCADIAN_SLEEP_START_HOUR,
    CIRCADIAN_SLEEP_END_HOUR,
    CIRCADIAN_TIMEZONE_OFFSET_HOURS,
    WARMUP_ROUTINE_ENABLED,
    WARMUP_INTERVAL_HOURS,
    MAINTENANCE_INTERVAL_HOURS,
    REQUIRED_PROFILE_REGEX,
    BRAND_FACTORY_ROUTINE_ENABLED,
    MAX_BRAND_ACCOUNTS_PER_PROFILE,
    MAX_BRAND_ACCOUNTS_PER_DAY_PER_PROFILE,
    BRAND_FACTORY_INTERVAL_HOURS,
)
from .database import (
    list_orders,
    get_subs_last_hour,
)
from .order_manager import (
    calculate_order_slots_today,
    process_order,
)

# ── Global State & Concurrency Guardrails ────────────────────────
_scheduler: Optional[BackgroundScheduler] = None
_tick_lock = threading.Lock()
_warmup_tick_lock = threading.Lock()
_maintenance_tick_lock = threading.Lock()
_factory_tick_lock = threading.Lock()
_is_paused = False
_last_tick_time: Optional[datetime.datetime] = None
_last_tick_summary: Dict[str, Any] = {
    "status": "idle",
    "timestamp": None,
    "orders_checked": 0,
    "sessions_attempted": 0,
    "successful": 0,
    "details": [],
}
_last_warmup_time: Optional[datetime.datetime] = None
_last_warmup_summary: Dict[str, Any] = {
    "status": "idle",
    "timestamp": None,
    "accounts_processed": 0,
    "successful": 0,
    "details": [],
}
_last_factory_time: Optional[datetime.datetime] = None
_last_factory_summary: Dict[str, Any] = {
    "status": "idle",
    "timestamp": None,
    "profiles_checked": 0,
    "accounts_created": 0,
    "details": [],
}


def is_circadian_sleep_time() -> bool:
    """
    Check if current local time (Vietnam UTC+7) falls within deep sleep hours (00:00 - 06:30).
    During sleep hours, subbing and video watching are paused to prevent bot pattern detection.
    """
    now_local = datetime.datetime.utcnow() + datetime.timedelta(hours=CIRCADIAN_TIMEZONE_OFFSET_HOURS)
    h = now_local.hour
    m = now_local.minute
    if CIRCADIAN_SLEEP_START_HOUR <= h < CIRCADIAN_SLEEP_END_HOUR:
        return True
    if h == CIRCADIAN_SLEEP_END_HOUR and m < 30:
        return True
    return False


def drip_feed_tick(dry_run: bool = False, local_db_path: str = LOCAL_DB_PATH, shared_db_path: str = SHARED_DB_PATH) -> Dict[str, Any]:
    """
    Core routine job executed periodically (e.g. every 15-30 minutes).
    Evaluates all active/running orders, enforces organic drip-feed pacing (1 sub per order per tick),
    and safely runs sub sessions without overlapping.
    """
    global _last_tick_time, _last_tick_summary

    if _is_paused:
        log("[SCHEDULER] Tick skipped: Scheduler is currently PAUSED.", "INFO")
        return {"status": "paused", "reason": "Scheduler is paused"}

    # Re-entrancy guardrail
    if not _tick_lock.acquire(blocking=False):
        log("[SCHEDULER] Tick skipped: A previous tick is still active in memory.", "WARN")
        return {"status": "busy", "reason": "Previous tick still running"}

    # Circadian sleep check
    if is_circadian_sleep_time() and not dry_run:
        _tick_lock.release()
        now_local = datetime.datetime.utcnow() + datetime.timedelta(hours=CIRCADIAN_TIMEZONE_OFFSET_HOURS)
        log(f"[SCHEDULER] Drip-feed skipped: Circadian Sleep Guard active (Local time: {now_local.strftime('%H:%M:%S')}).", "INFO")
        return {"status": "sleep_hours", "reason": "Circadian sleep period active (00:00 - 06:30)"}

    now_utc = datetime.datetime.utcnow()
    _last_tick_time = now_utc
    log("═════════════════════════════════════════════════════════════════", "INFO")
    log(f"[SCHEDULER] Drip-feed Routine Tick started at {now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')} (Dry-run: {dry_run})", "INFO")
    log("═════════════════════════════════════════════════════════════════", "INFO")

    tick_result = {
        "status": "completed",
        "timestamp": now_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "dry_run": dry_run,
        "orders_checked": 0,
        "sessions_attempted": 0,
        "successful": 0,
        "details": [],
    }

    try:
        # Check running or pending orders
        candidate_orders = list_orders(status="running", db_path=local_db_path)
        # If no running orders, check pending orders to initiate
        if not candidate_orders:
            pending = list_orders(status="pending", db_path=local_db_path)
            candidate_orders.extend(pending)

        tick_result["orders_checked"] = len(candidate_orders)
        if not candidate_orders:
            log("[SCHEDULER] No active/running orders in queue. Routine tick finished.", "INFO")
            _last_tick_summary = tick_result
            return tick_result

        for ord_info in candidate_orders:
            order_id = ord_info["id"]
            channel_id = ord_info.get("channel_id") or ord_info.get("channel_url", "")

            # 1. Check Hourly Velocity Guardrail (max 3/h)
            recent_subs = get_subs_last_hour(channel_id, db_path=local_db_path)
            if recent_subs >= MAX_SUBS_PER_CHANNEL_PER_HOUR:
                log(f"[SCHEDULER] Order #{order_id} ({channel_id}) reached hourly velocity cap ({recent_subs}/{MAX_SUBS_PER_CHANNEL_PER_HOUR}). Skipping this tick.", "INFO")
                tick_result["details"].append({
                    "order_id": order_id,
                    "action": "skip",
                    "reason": f"Hourly velocity cap reached ({recent_subs}/{MAX_SUBS_PER_CHANNEL_PER_HOUR})",
                })
                continue

            # 2. Check Effective Daily Slots (with S-Curve modeling)
            slots_available = calculate_order_slots_today(
                order_id,
                db_path=local_db_path,
                apply_drip_feed=True,
            )
            if slots_available <= 0:
                log(f"[SCHEDULER] Order #{order_id} has no available slots today. Skipping this tick.", "INFO")
                tick_result["details"].append({
                    "order_id": order_id,
                    "action": "skip",
                    "reason": "Daily quota filled or target reached",
                })
                continue

            # 3. True Drip-feed: Execute exactly 1 subscription session for this channel in this tick
            log(f"[SCHEDULER] Dispatching 1 drip-feed slot for Order #{order_id} ({channel_id})...", "INFO")
            proc_res = process_order(
                order_id=order_id,
                max_subs=1,
                dry_run=dry_run,
                shared_db_path=shared_db_path,
                local_db_path=local_db_path,
                apply_drip_feed=True,
            )

            sessions_done = proc_res.get("assigned_count", 0)
            success_done = proc_res.get("successful_count", 0)
            tick_result["sessions_attempted"] += sessions_done
            tick_result["successful"] += success_done
            tick_result["details"].append({
                "order_id": order_id,
                "action": "executed",
                "assigned": sessions_done,
                "successful": success_done,
                "status": proc_res.get("status"),
            })

    except Exception as e:
        log(f"[SCHEDULER] Error during routine tick: {e}", "ERROR")
        tick_result["status"] = "error"
        tick_result["error"] = str(e)

    finally:
        _tick_lock.release()
        _last_tick_summary = tick_result
        log(f"[SCHEDULER] Routine Tick complete: {tick_result['successful']}/{tick_result['sessions_attempted']} successful sessions.", "SUCCESS")

    return tick_result


# ── Autonomous Warmup Routine ────────────────────────────────────

def warmup_routine_tick(
    dry_run: bool = False,
    shared_db_path: str = SHARED_DB_PATH,
    duration_minutes: int = 5,
) -> Dict[str, Any]:
    """
    Autonomous routine tick to nurture 'cold' and 'warming' brand accounts.
    Scans accounts pool for candidate brand accounts belonging to allowed profiles (sub_yt-x),
    runs humanized video viewing session, and promotes trust levels.
    """
    global _last_warmup_time, _last_warmup_summary

    if not WARMUP_ROUTINE_ENABLED:
        log("[SCHEDULER] Warmup tick skipped: WARMUP_ROUTINE_ENABLED is False.", "INFO")
        return {"status": "disabled", "reason": "Warmup routine disabled"}

    if _is_paused:
        log("[SCHEDULER] Warmup tick skipped: Scheduler is paused.", "INFO")
        return {"status": "paused", "reason": "Scheduler is paused"}

    if not _warmup_tick_lock.acquire(blocking=False):
        log("[SCHEDULER] Warmup tick skipped: Another warmup tick is currently running.", "WARN")
        return {"status": "busy", "reason": "Previous warmup tick still running"}

    # Circadian sleep check
    if is_circadian_sleep_time() and not dry_run:
        _warmup_tick_lock.release()
        now_local = datetime.datetime.utcnow() + datetime.timedelta(hours=CIRCADIAN_TIMEZONE_OFFSET_HOURS)
        log(f"[SCHEDULER] Warmup tick skipped: Circadian Sleep Guard active (Local time: {now_local.strftime('%H:%M:%S')}).", "INFO")
        return {"status": "sleep_hours", "reason": "Circadian sleep period active (00:00 - 06:30)"}

    now_utc = datetime.datetime.utcnow()
    _last_warmup_time = now_utc
    log("═════════════════════════════════════════════════════════════════", "INFO")
    log(f"[SCHEDULER] Autonomous Warmup Routine Tick started at {now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')} (Dry-run: {dry_run})", "INFO")
    log("═════════════════════════════════════════════════════════════════", "INFO")

    warmup_result = {
        "status": "completed",
        "timestamp": now_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "dry_run": dry_run,
        "accounts_processed": 0,
        "successful": 0,
        "details": [],
    }

    try:
        # 1. Fetch candidate brand accounts needing nurture
        conn = sqlite3.connect(shared_db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, gpm_profile_id, switch_name, niche, warmup_status, warmup_days, warmup_videos
            FROM sub_accounts
            WHERE warmup_status IN ('cold', 'warming') AND is_active = 1
            ORDER BY warmup_videos ASC, id ASC;
            """
        )
        candidates = [dict(r) for r in cur.fetchall()]
        conn.close()

        if not candidates:
            log("[SCHEDULER] No 'cold' or 'warming' accounts found in database. Warmup tick complete.", "INFO")
            _last_warmup_summary = warmup_result
            return warmup_result

        # Import automation dependencies safely
        if r"D:\VibeCoding\nuoi-kenh-youtube" not in sys.path:
            sys.path.append(r"D:\VibeCoding\nuoi-kenh-youtube")
        from nuoi_kenh.brand_account_manager import warmup_brand_account_session
        from nuoi_kenh.gpm_api import mo_profile_gpm, dong_profile_gpm, lay_tat_ca_profiles

        all_profiles = lay_tat_ca_profiles()
        name_map = {p.get("id"): p.get("name") for p in all_profiles if isinstance(p, dict)}

        for acc in candidates:
            acc_id = acc["id"]
            prof_id = acc["gpm_profile_id"]
            prof_name = name_map.get(prof_id, "")

            # Fallback: Query gpm_profiles table in database
            if not prof_name:
                try:
                    c_conn = sqlite3.connect(shared_db_path)
                    c_cur = c_conn.cursor()
                    c_cur.execute("SELECT name FROM gpm_profiles WHERE id = ?;", (prof_id,))
                    p_row = c_cur.fetchone()
                    if p_row and p_row[0]:
                        prof_name = p_row[0]
                    c_conn.close()
                except Exception:
                    pass

            switch_name = acc["switch_name"]
            niche = acc["niche"] or "general"

            # Profile pattern guardrail
            if not re.match(REQUIRED_PROFILE_REGEX, prof_name or ""):
                log(f"[SCHEDULER] Skipping Account #{acc_id}: Profile '{prof_name}' does not match pattern '{REQUIRED_PROFILE_REGEX}'.", "WARN")
                continue

            warmup_result["accounts_processed"] += 1
            log(f"[SCHEDULER] Running Warmup Session for Account #{acc_id} ('{switch_name}', niche: {niche}) on profile '{prof_name}'...", "INFO")

            if dry_run:
                warmup_result["successful"] += 1
                warmup_result["details"].append({
                    "account_id": acc_id,
                    "profile_name": prof_name,
                    "switch_name": switch_name,
                    "status": "dry_run_success",
                })
                continue

            # Open GPM Profile
            driver = mo_profile_gpm(prof_id)
            if not driver:
                log(f"[SCHEDULER] Could not open profile '{prof_name}' for Account #{acc_id}.", "ERROR")
                warmup_result["details"].append({
                    "account_id": acc_id,
                    "profile_name": prof_name,
                    "status": "failed_open_browser",
                })
                continue

            try:
                res = warmup_brand_account_session(
                    driver=driver,
                    sub_account_id=acc_id,
                    niche=niche,
                    duration_minutes=duration_minutes,
                    db_path=shared_db_path,
                )
                if res.get("status") in ("COMPLETED", "SUCCESS"):
                    warmup_result["successful"] += 1
                    warmup_result["details"].append({
                        "account_id": acc_id,
                        "profile_name": prof_name,
                        "status": "success",
                        "videos_watched": res.get("videos_watched", 1),
                    })
                else:
                    warmup_result["details"].append({
                        "account_id": acc_id,
                        "profile_name": prof_name,
                        "status": res.get("status", "failed"),
                    })
            except Exception as e:
                log(f"[SCHEDULER] Error during warmup session for Account #{acc_id}: {e}", "ERROR")
                warmup_result["details"].append({
                    "account_id": acc_id,
                    "profile_name": prof_name,
                    "status": "exception",
                    "error": str(e),
                })
            finally:
                dong_profile_gpm(prof_id)

    except Exception as e:
        log(f"[SCHEDULER] Error during warmup routine tick: {e}", "ERROR")
        warmup_result["status"] = "error"
        warmup_result["error"] = str(e)
    finally:
        _warmup_tick_lock.release()
        _last_warmup_summary = warmup_result
        log(f"[SCHEDULER] Autonomous Warmup Tick complete: {warmup_result['successful']}/{warmup_result['accounts_processed']} accounts warmed.", "SUCCESS")

    return warmup_result


def maintenance_routine_tick(shared_db_path: str = SHARED_DB_PATH) -> Dict[str, Any]:
    """
    Periodic maintenance job to clean expired account locks and stale state.
    """
    if not _maintenance_tick_lock.acquire(blocking=False):
        return {"status": "busy", "reason": "Maintenance tick already running"}

    log("[SCHEDULER] Running Periodic Maintenance Routine...", "INFO")
    cleared_locks = 0
    try:
        conn = sqlite3.connect(shared_db_path)
        cur = conn.cursor()
        cur.execute("DELETE FROM account_locks WHERE expires_at <= datetime('now');")
        cleared_locks = cur.rowcount
        conn.commit()
        conn.close()
        log(f"[SCHEDULER] Maintenance complete: Cleared {cleared_locks} expired account locks.", "SUCCESS")
    except Exception as e:
        log(f"[SCHEDULER] Error during maintenance tick: {e}", "ERROR")
    finally:
        _maintenance_tick_lock.release()

    return {"status": "completed", "cleared_locks": cleared_locks}


# ── Autonomous Brand Account Factory Routine ─────────────────────

def brand_account_factory_tick(
    dry_run: bool = False,
    shared_db_path: str = SHARED_DB_PATH,
) -> Dict[str, Any]:
    """
    Autonomous routine tick to create new Brand Accounts for eligible sub_yt-x profiles.
    Enforces daily quota (max 1/day/profile) and profile ceiling (max 4/profile)
    to prevent Google SMS checkpoint triggers.
    """
    global _last_factory_time, _last_factory_summary

    if not BRAND_FACTORY_ROUTINE_ENABLED:
        log("[SCHEDULER] Brand factory tick skipped: BRAND_FACTORY_ROUTINE_ENABLED is False.", "INFO")
        return {"status": "disabled", "reason": "Brand factory routine disabled"}

    if _is_paused:
        log("[SCHEDULER] Brand factory tick skipped: Scheduler is paused.", "INFO")
        return {"status": "paused", "reason": "Scheduler is paused"}

    if not _factory_tick_lock.acquire(blocking=False):
        log("[SCHEDULER] Brand factory tick skipped: Another factory tick is currently running.", "WARN")
        return {"status": "busy", "reason": "Previous factory tick still running"}

    if is_circadian_sleep_time() and not dry_run:
        _factory_tick_lock.release()
        now_local = datetime.datetime.utcnow() + datetime.timedelta(hours=CIRCADIAN_TIMEZONE_OFFSET_HOURS)
        log(f"[SCHEDULER] Brand factory tick skipped: Circadian Sleep Guard active (Local time: {now_local.strftime('%H:%M:%S')}).", "INFO")
        return {"status": "sleep_hours", "reason": "Circadian sleep period active (00:00 - 06:30)"}

    now_utc = datetime.datetime.utcnow()
    _last_factory_time = now_utc
    log("═════════════════════════════════════════════════════════════════", "INFO")
    log(f"[SCHEDULER] Brand Account Factory Routine Tick started at {now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')} (Dry-run: {dry_run})", "INFO")
    log("═════════════════════════════════════════════════════════════════", "INFO")

    factory_result = {
        "status": "completed",
        "timestamp": now_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "dry_run": dry_run,
        "profiles_checked": 0,
        "accounts_created": 0,
        "details": [],
    }

    try:
        # 1. Fetch eligible profiles matching REQUIRED_PROFILE_REGEX (^sub_yt-\d+$)
        conn = sqlite3.connect(shared_db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        try:
            cur.execute("SELECT id, name FROM gpm_profiles WHERE status = 'active' OR status IS NULL;")
            profiles_db = [dict(r) for r in cur.fetchall()]
        except sqlite3.OperationalError:
            cur.execute("SELECT id, notes, gmail FROM gpm_profiles WHERE is_active = 1;")
            raw_profiles = [dict(r) for r in cur.fetchall()]
            profiles_db = []
            for r in raw_profiles:
                p_name = ""
                notes = r.get("notes") or ""
                if "Discovered:" in notes:
                    p_name = notes.split("Discovered:")[-1].strip()
                elif r.get("gmail"):
                    p_name = r["gmail"].split("@")[0]
                profiles_db.append({"id": r["id"], "name": p_name})
        conn.close()

        name_map = {p["id"]: p.get("name", "") for p in profiles_db}
        if r"D:\VibeCoding\nuoi-kenh-youtube" not in sys.path:
            sys.path.append(r"D:\VibeCoding\nuoi-kenh-youtube")
        try:
            from nuoi_kenh.gpm_api import lay_tat_ca_profiles
            api_profs = lay_tat_ca_profiles()
            api_map = {ap.get("id"): ap.get("name", "") for ap in api_profs if isinstance(ap, dict) and ap.get("id")}
            for pid in name_map:
                if not name_map[pid] and pid in api_map:
                    name_map[pid] = api_map[pid]
            if not profiles_db:
                for ap in api_profs:
                    if isinstance(ap, dict) and ap.get("id"):
                        name_map[ap["id"]] = ap.get("name", "")
                        profiles_db.append({"id": ap["id"], "name": ap.get("name", "")})
        except Exception as e:
            log(f"[SCHEDULER] GPM API lay_tat_ca_profiles fallback: {e}", "DEBUG")

        eligible_profiles = []
        for prof in profiles_db:
            prof_id = prof["id"]
            prof_name = name_map.get(prof_id) or prof.get("name", "")
            if prof_name and re.match(REQUIRED_PROFILE_REGEX, prof_name):
                eligible_profiles.append({"id": prof_id, "name": prof_name})

        factory_result["profiles_checked"] = len(eligible_profiles)
        if not eligible_profiles:
            log(f"[SCHEDULER] No profiles found matching pattern '{REQUIRED_PROFILE_REGEX}'. Factory tick complete.", "INFO")
            _last_factory_summary = factory_result
            return factory_result

        # Import factory dependencies
        from nuoi_kenh.brand_account_manager import (
            generate_channel_name,
            create_brand_account,
            NICHE_TEMPLATES,
        )
        from nuoi_kenh.gpm_api import mo_profile_gpm, dong_profile_gpm
        import random

        all_niches = list(NICHE_TEMPLATES.keys())

        for prof in eligible_profiles:
            prof_id = prof["id"]
            prof_name = prof["name"]

            conn = sqlite3.connect(shared_db_path)
            cur = conn.cursor()

            # Profile ceiling check
            cur.execute(
                """
                SELECT COUNT(*) FROM sub_accounts
                WHERE gpm_profile_id = ? AND account_type = 'brand_account' AND is_active = 1;
                """,
                (prof_id,)
            )
            brand_count = cur.fetchone()[0]

            if brand_count >= MAX_BRAND_ACCOUNTS_PER_PROFILE:
                log(f"[SCHEDULER] Profile '{prof_name}' reached max brand accounts ({brand_count}/{MAX_BRAND_ACCOUNTS_PER_PROFILE}). Skipping.", "INFO")
                factory_result["details"].append({
                    "profile_id": prof_id,
                    "profile_name": prof_name,
                    "action": "skip",
                    "reason": f"Max brand accounts reached ({brand_count}/{MAX_BRAND_ACCOUNTS_PER_PROFILE})",
                })
                conn.close()
                continue

            # Daily limit check: max 1/day/profile
            cur.execute(
                """
                SELECT COUNT(*) FROM sub_accounts
                WHERE gpm_profile_id = ? AND account_type = 'brand_account'
                  AND created_at >= datetime('now', '-24 hours');
                """,
                (prof_id,)
            )
            created_last_24h = cur.fetchone()[0]

            if created_last_24h >= MAX_BRAND_ACCOUNTS_PER_DAY_PER_PROFILE:
                log(f"[SCHEDULER] Profile '{prof_name}' already created {created_last_24h} brand account(s) in last 24h. Skipping.", "INFO")
                factory_result["details"].append({
                    "profile_id": prof_id,
                    "profile_name": prof_name,
                    "action": "skip",
                    "reason": f"Daily creation cap reached ({created_last_24h}/{MAX_BRAND_ACCOUNTS_PER_DAY_PER_PROFILE})",
                })
                conn.close()
                continue

            # Pick niche: prioritize unused niches on this profile
            cur.execute(
                """
                SELECT DISTINCT niche FROM sub_accounts
                WHERE gpm_profile_id = ? AND is_active = 1;
                """,
                (prof_id,)
            )
            used_niches = {row[0] for row in cur.fetchall() if row[0]}
            conn.close()

            available_niches = [n for n in all_niches if n not in used_niches]
            selected_niche = random.choice(available_niches) if available_niches else random.choice(all_niches)
            new_channel_name = generate_channel_name(niche=selected_niche)

            log(f"[SCHEDULER] Creating Brand Account '{new_channel_name}' (niche: {selected_niche}) for profile '{prof_name}'...", "INFO")

            if dry_run:
                factory_result["accounts_created"] += 1
                factory_result["details"].append({
                    "profile_id": prof_id,
                    "profile_name": prof_name,
                    "channel_name": new_channel_name,
                    "niche": selected_niche,
                    "status": "dry_run_success",
                })
                continue

            # Open GPM Profile
            driver = mo_profile_gpm(prof_id)
            if not driver:
                log(f"[SCHEDULER] Could not open profile '{prof_name}' for brand creation.", "ERROR")
                factory_result["details"].append({
                    "profile_id": prof_id,
                    "profile_name": prof_name,
                    "status": "failed_open_browser",
                })
                continue

            try:
                res = create_brand_account(
                    driver=driver,
                    profile_id=prof_id,
                    channel_name=new_channel_name,
                    niche=selected_niche,
                    db_path=shared_db_path,
                )
                if res.get("status") == "SUCCESS":
                    factory_result["accounts_created"] += 1
                    factory_result["details"].append({
                        "profile_id": prof_id,
                        "profile_name": prof_name,
                        "account_id": res.get("account_id"),
                        "channel_name": res.get("channel_name"),
                        "channel_id": res.get("channel_id"),
                        "niche": selected_niche,
                        "status": "success",
                    })
                    log(f"[SCHEDULER] Successfully created Brand Account '{res.get('channel_name')}' on '{prof_name}'.", "SUCCESS")
                else:
                    factory_result["details"].append({
                        "profile_id": prof_id,
                        "profile_name": prof_name,
                        "channel_name": new_channel_name,
                        "status": res.get("status", "failed"),
                        "error": res.get("error"),
                    })
                    log(f"[SCHEDULER] Brand creation returned status: {res.get('status')}, error: {res.get('error')}", "WARN")
            except Exception as e:
                log(f"[SCHEDULER] Exception during brand account creation for '{prof_name}': {e}", "ERROR")
                factory_result["details"].append({
                    "profile_id": prof_id,
                    "profile_name": prof_name,
                    "channel_name": new_channel_name,
                    "status": "exception",
                    "error": str(e),
                })
            finally:
                dong_profile_gpm(prof_id)

    except Exception as e:
        log(f"[SCHEDULER] Error during brand factory routine tick: {e}", "ERROR")
        factory_result["status"] = "error"
        factory_result["error"] = str(e)
    finally:
        _factory_tick_lock.release()
        _last_factory_summary = factory_result
        log(f"[SCHEDULER] Brand Account Factory Tick complete: {factory_result['accounts_created']} created across {factory_result['profiles_checked']} profiles.", "SUCCESS")

    return factory_result


# ── Scheduler Lifecycle Controls ─────────────────────────────────

def get_scheduler() -> BackgroundScheduler:
    """Return the global BackgroundScheduler instance, creating it if needed."""
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(
            daemon=True,
            timezone="UTC",
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
            },
        )
    return _scheduler


def start_scheduler(
    tick_minutes: Optional[int] = None,
    dry_run: bool = False,
    local_db_path: str = LOCAL_DB_PATH,
    shared_db_path: str = SHARED_DB_PATH,
) -> bool:
    """
    Start the autonomous routine scheduler if not already running.
    Registers drip-feed subbing, warmup routine, and maintenance jobs.
    """
    global _is_paused
    sched = get_scheduler()
    interval_min = tick_minutes or SCHEDULER_TICK_INTERVAL_MINUTES

    if sched.running:
        log("[SCHEDULER] Scheduler is already running.", "INFO")
        _is_paused = False
        return True

    # 1. Register Drip-Feed Routine
    trigger_drip = IntervalTrigger(minutes=interval_min)
    sched.add_job(
        drip_feed_tick,
        trigger=trigger_drip,
        id="drip_feed_routine_tick",
        name="YouTube Drip-Feed Routine Tick",
        replace_existing=True,
        kwargs={"dry_run": dry_run, "local_db_path": local_db_path, "shared_db_path": shared_db_path},
    )

    # 2. Register Warmup Routine
    if WARMUP_ROUTINE_ENABLED:
        trigger_warmup = IntervalTrigger(hours=WARMUP_INTERVAL_HOURS)
        sched.add_job(
            warmup_routine_tick,
            trigger=trigger_warmup,
            id="warmup_routine_tick",
            name="Autonomous Warmup Routine Tick",
            replace_existing=True,
            kwargs={"dry_run": dry_run, "shared_db_path": shared_db_path},
        )

    # 3. Register Maintenance Routine
    trigger_maint = IntervalTrigger(hours=MAINTENANCE_INTERVAL_HOURS)
    sched.add_job(
        maintenance_routine_tick,
        trigger=trigger_maint,
        id="maintenance_routine_tick",
        name="System Maintenance Routine Tick",
        replace_existing=True,
        kwargs={"shared_db_path": shared_db_path},
    )

    # 4. Register Brand Account Factory Routine
    if BRAND_FACTORY_ROUTINE_ENABLED:
        trigger_factory = IntervalTrigger(hours=BRAND_FACTORY_INTERVAL_HOURS)
        sched.add_job(
            brand_account_factory_tick,
            trigger=trigger_factory,
            id="brand_account_factory_tick",
            name="Autonomous Brand Account Factory Routine Tick",
            replace_existing=True,
            kwargs={"dry_run": dry_run, "shared_db_path": shared_db_path},
        )

    sched.start()
    _is_paused = False
    log(f"[SCHEDULER] Background scheduler started successfully (Drip: every {interval_min}m, Warmup: every {WARMUP_INTERVAL_HOURS}h, Maint: every {MAINTENANCE_INTERVAL_HOURS}h, Factory: every {BRAND_FACTORY_INTERVAL_HOURS}h).", "SUCCESS")
    return True


def stop_scheduler() -> bool:
    """Stop the scheduler and clean up background threads."""
    global _scheduler, _is_paused
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        _is_paused = False
        log("[SCHEDULER] Background scheduler shut down.", "INFO")
        return True
    return False


def pause_scheduler() -> bool:
    """Pause job execution in the scheduler."""
    global _is_paused
    _is_paused = True
    sched = get_scheduler()
    if sched.running:
        sched.pause()
        log("[SCHEDULER] Scheduler paused.", "INFO")
        return True
    return False


def resume_scheduler() -> bool:
    """Resume job execution in the scheduler."""
    global _is_paused
    _is_paused = False
    sched = get_scheduler()
    if sched.running:
        sched.resume()
        log("[SCHEDULER] Scheduler resumed.", "INFO")
        return True
    return False


def trigger_tick_now(
    dry_run: bool = False,
    local_db_path: str = LOCAL_DB_PATH,
    shared_db_path: str = SHARED_DB_PATH,
) -> Dict[str, Any]:
    """Manually invoke a routine drip-feed tick immediately outside the schedule."""
    log("[SCHEDULER] Manual drip-feed tick triggered on-demand.", "INFO")
    return drip_feed_tick(dry_run=dry_run, local_db_path=local_db_path, shared_db_path=shared_db_path)


def trigger_warmup_tick_now(
    dry_run: bool = False,
    shared_db_path: str = SHARED_DB_PATH,
    duration_minutes: int = 5,
) -> Dict[str, Any]:
    """Manually invoke a warmup routine tick immediately outside the schedule."""
    log("[SCHEDULER] Manual warmup tick triggered on-demand.", "INFO")
    return warmup_routine_tick(dry_run=dry_run, shared_db_path=shared_db_path, duration_minutes=duration_minutes)


def trigger_maintenance_tick_now(shared_db_path: str = SHARED_DB_PATH) -> Dict[str, Any]:
    """Manually invoke a maintenance routine tick immediately outside the schedule."""
    log("[SCHEDULER] Manual maintenance tick triggered on-demand.", "INFO")
    return maintenance_routine_tick(shared_db_path=shared_db_path)


def trigger_factory_tick_now(
    dry_run: bool = False,
    shared_db_path: str = SHARED_DB_PATH,
) -> Dict[str, Any]:
    """Manually invoke a brand account factory routine tick immediately outside the schedule."""
    log("[SCHEDULER] Manual brand factory tick triggered on-demand.", "INFO")
    return brand_account_factory_tick(dry_run=dry_run, shared_db_path=shared_db_path)


def get_scheduler_status() -> Dict[str, Any]:
    """Retrieve runtime state and metrics of the scheduler across all registered jobs."""
    sched = get_scheduler()
    is_running = sched.running
    jobs = sched.get_jobs()
    next_runs = {}

    for job in jobs:
        if job.next_run_time:
            next_runs[job.id] = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S UTC")

    now_local = datetime.datetime.utcnow() + datetime.timedelta(hours=CIRCADIAN_TIMEZONE_OFFSET_HOURS)

    return {
        "is_running": is_running,
        "is_paused": _is_paused,
        "is_circadian_sleep": is_circadian_sleep_time(),
        "local_time": now_local.strftime("%Y-%m-%d %H:%M:%S (UTC+7)"),
        "tick_interval_minutes": SCHEDULER_TICK_INTERVAL_MINUTES,
        "active_jobs_count": len(jobs),
        "registered_jobs": [job.id for job in jobs],
        "next_run_time": next_runs.get("drip_feed_routine_tick"),
        "next_runs": next_runs,
        "last_tick_time": _last_tick_time.strftime("%Y-%m-%d %H:%M:%S UTC") if _last_tick_time else None,
        "last_tick_summary": _last_tick_summary,
        "last_warmup_time": _last_warmup_time.strftime("%Y-%m-%d %H:%M:%S UTC") if _last_warmup_time else None,
        "last_warmup_summary": _last_warmup_summary,
        "last_factory_time": _last_factory_time.strftime("%Y-%m-%d %H:%M:%S UTC") if _last_factory_time else None,
        "last_factory_summary": _last_factory_summary,
    }

