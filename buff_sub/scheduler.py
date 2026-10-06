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

from .logger import log
from .config import (
    SCHEDULER_TICK_INTERVAL_MINUTES,
    MAX_SUBS_PER_CHANNEL_PER_HOUR,
    LOCAL_DB_PATH,
    SHARED_DB_PATH,
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
    Adds the drip_feed_tick job at configured interval.
    """
    global _is_paused
    sched = get_scheduler()
    interval_min = tick_minutes or SCHEDULER_TICK_INTERVAL_MINUTES

    if sched.running:
        log("[SCHEDULER] Scheduler is already running.", "INFO")
        _is_paused = False
        return True

    # Register the routine tick job
    trigger = IntervalTrigger(minutes=interval_min)
    sched.add_job(
        drip_feed_tick,
        trigger=trigger,
        id="drip_feed_routine_tick",
        name="YouTube Drip-Feed Routine Tick",
        replace_existing=True,
        kwargs={"dry_run": dry_run, "local_db_path": local_db_path, "shared_db_path": shared_db_path},
    )

    sched.start()
    _is_paused = False
    log(f"[SCHEDULER] Background scheduler started successfully (Interval: every {interval_min} minutes).", "SUCCESS")
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
    """Manually invoke a routine tick immediately outside the schedule."""
    log("[SCHEDULER] Manual tick triggered on-demand.", "INFO")
    return drip_feed_tick(dry_run=dry_run, local_db_path=local_db_path, shared_db_path=shared_db_path)


def get_scheduler_status() -> Dict[str, Any]:
    """Retrieve runtime state and metrics of the scheduler."""
    sched = get_scheduler()
    is_running = sched.running
    jobs = sched.get_jobs()
    next_run = None

    for job in jobs:
        if job.id == "drip_feed_routine_tick" and job.next_run_time:
            next_run = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S UTC")

    return {
        "is_running": is_running,
        "is_paused": _is_paused,
        "tick_interval_minutes": SCHEDULER_TICK_INTERVAL_MINUTES,
        "active_jobs_count": len(jobs),
        "next_run_time": next_run,
        "last_tick_time": _last_tick_time.strftime("%Y-%m-%d %H:%M:%S UTC") if _last_tick_time else None,
        "last_tick_summary": _last_tick_summary,
    }
