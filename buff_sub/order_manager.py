# -*- coding: utf-8 -*-
"""
order_manager.py — Subscription Order Allocation & Execution Coordinator
Calculates daily/hourly capacity, enforces Anti-Clustering diversity,
and dispatches subscription sessions through sub_engine.
"""
import time
import random
from typing import Optional, List, Dict, Any, Set

from .logger import log
from .config import (
    SHARED_DB_PATH,
    LOCAL_DB_PATH,
    MAX_SUBS_PER_CHANNEL_PER_HOUR,
)
from .database import (
    get_order,
    list_orders,
    update_order_status,
    get_delivered_today,
    get_subs_last_hour,
    has_account_subbed,
)
from .account_pool import get_ready_accounts
from .sub_engine import run_sub_session
from .drip_feed import calculate_effective_daily_cap


def calculate_order_slots_today(
    order_id: int,
    db_path: str = LOCAL_DB_PATH,
    apply_drip_feed: bool = False,
) -> int:
    """
    Calculate how many subscription slots can be delivered today for an order.
    Considers remaining target subs and remaining daily quota.
    When apply_drip_feed is True, applies S-Curve scaling based on order age.
    Returns 0 if order is paused, completed, or daily cap is exhausted.
    """
    order = get_order(order_id, db_path=db_path)
    if not order:
        return 0

    status = order.get("status", "pending")
    if status in ("paused", "completed", "failed"):
        log(f"Order #{order_id} is '{status}'. No slots available.", "INFO")
        return 0

    target = order.get("target_subs", 0)
    delivered = order.get("delivered", 0)
    remaining_target = max(0, target - delivered)
    if remaining_target <= 0:
        log(f"Order #{order_id} target reached ({delivered}/{target}).", "SUCCESS")
        return 0

    if apply_drip_feed:
        effective_daily_cap = calculate_effective_daily_cap(order)
    else:
        effective_daily_cap = int(order.get("daily_cap") or 20)

    delivered_today = get_delivered_today(order_id, db_path=db_path)
    remaining_today = max(0, effective_daily_cap - delivered_today)

    available_slots = min(remaining_target, remaining_today)
    log(
        f"Order #{order_id} slots today: {available_slots} "
        f"(Target remaining: {remaining_target}, Daily quota left: {remaining_today}/{effective_daily_cap} [drip: {apply_drip_feed}])",
        "INFO",
    )
    return available_slots


def assign_accounts_to_order(
    order_id: int,
    max_slots: Optional[int] = None,
    shared_db_path: str = SHARED_DB_PATH,
    local_db_path: str = LOCAL_DB_PATH,
    apply_drip_feed: bool = False,
) -> List[Dict[str, Any]]:
    """
    Select and assign eligible accounts to fulfill an order session.
    Enforces Anti-Clustering guardrails:
      1. Hourly velocity limit (max 2-3 subs per channel per hour)
      2. Duplicate exclusion (skip accounts that already subbed this channel)
      3. Master Gmail Diversity (max 1 account per GPM profile in the batch)
      4. Trust Tier priority (gmail_root before brand_account)
    """
    order = get_order(order_id, db_path=local_db_path)
    if not order:
        log(f"Order #{order_id} not found.", "ERROR")
        return []

    channel_id = order.get("channel_id") or order.get("channel_url", "")

    # 1. Check daily slot limit
    slots_today = calculate_order_slots_today(
        order_id,
        db_path=local_db_path,
        apply_drip_feed=apply_drip_feed,
    )
    if slots_today <= 0:
        return []

    requested_slots = min(slots_today, max_slots) if max_slots is not None else slots_today

    # 2. Check hourly velocity limit
    subs_in_last_hour = get_subs_last_hour(channel_id, db_path=local_db_path)
    if subs_in_last_hour >= MAX_SUBS_PER_CHANNEL_PER_HOUR:
        log(
            f"Hourly Anti-Clustering threshold reached for {channel_id}: "
            f"{subs_in_last_hour}/{MAX_SUBS_PER_CHANNEL_PER_HOUR} subs in past hour. Postponing allocation.",
            "WARN",
        )
        return []

    max_allowed_this_hour = MAX_SUBS_PER_CHANNEL_PER_HOUR - subs_in_last_hour
    target_allocation = min(requested_slots, max_allowed_this_hour)

    log(
        f"Allocating up to {target_allocation} accounts for Order #{order_id} "
        f"(Hourly budget left: {max_allowed_this_hour})",
        "INFO",
    )

    # 3. Fetch candidate accounts from shared pool (fetch 3x candidate pool to allow filtering)
    candidates = get_ready_accounts(
        limit=target_allocation * 3,
        db_path=shared_db_path,
    )

    assigned: List[Dict[str, Any]] = []
    used_gpm_profiles: Set[str] = set()

    for acc in candidates:
        acc_id = acc["id"]
        gpm_id = acc["gpm_profile_id"]

        # Diversity constraint: 1 account per master GPM profile in batch
        if gpm_id in used_gpm_profiles:
            continue

        # Duplicate check: has this account subbed this channel before?
        if has_account_subbed(acc_id, channel_id, db_path=local_db_path):
            log(f"Account #{acc_id} has already subscribed to {channel_id}. Skipping.", "INFO")
            continue

        assigned.append(acc)
        used_gpm_profiles.add(gpm_id)

        if len(assigned) >= target_allocation:
            break

    log(f"Assigned {len(assigned)} diverse accounts for Order #{order_id}.", "SUCCESS")
    return assigned


def process_order(
    order_id: int,
    max_subs: Optional[int] = None,
    dry_run: bool = False,
    shared_db_path: str = SHARED_DB_PATH,
    local_db_path: str = LOCAL_DB_PATH,
    apply_drip_feed: bool = False,
) -> Dict[str, Any]:
    """
    Process an order by assigning available accounts and executing sub sessions.
    Runs assigned accounts sequentially with organic inter-session jitter.
    """
    order = get_order(order_id, db_path=local_db_path)
    if not order:
        return {
            "order_id": order_id,
            "status": "error",
            "message": f"Order #{order_id} does not exist",
        }

    # Automatically set status to running if pending
    if order.get("status") == "pending":
        update_order_status(order_id, "running", db_path=local_db_path)

    assigned_accounts = assign_accounts_to_order(
        order_id=order_id,
        max_slots=max_subs,
        shared_db_path=shared_db_path,
        local_db_path=local_db_path,
        apply_drip_feed=apply_drip_feed,
    )

    if not assigned_accounts:
        log(f"No accounts could be assigned for Order #{order_id} at this time.", "WARN")
        return {
            "order_id": order_id,
            "status": "idle",
            "message": "No accounts available (daily cap reached, hourly rate limit, or no ready accounts)",
            "assigned_count": 0,
            "successful_count": 0,
            "session_results": [],
        }

    log(f"Starting execution run for Order #{order_id} with {len(assigned_accounts)} accounts...", "INFO")
    successful_runs = 0
    failed_runs = 0
    session_results = []

    for index, acc in enumerate(assigned_accounts, 1):
        acc_id = acc["id"]
        gpm_id = acc["gpm_profile_id"]
        handle = acc.get("channel_id") or acc.get("switch_name", "unknown")

        log(f"[{index}/{len(assigned_accounts)}] Executing session with Account #{acc_id} ({handle})...", "INFO")

        res = run_sub_session(
            gpm_profile_id=gpm_id,
            account_id=acc_id,
            order_id=order_id,
            dry_run=dry_run,
        )
        session_results.append(res)

        if res.get("sub_success"):
            successful_runs += 1
        else:
            failed_runs += 1

        # Check if order completed early
        current_order = get_order(order_id, db_path=local_db_path)
        if current_order and current_order.get("status") == "completed":
            log(f"Order #{order_id} reached 100% completion target during batch. Stopping.", "SUCCESS")
            break

        # Inter-session organic jitter delay (skip in dry-run for speed)
        if index < len(assigned_accounts):
            if dry_run:
                time.sleep(0.5)
            else:
                jitter = random.uniform(8.0, 18.0)
                log(f"Inter-session jitter pause: {jitter:.1f}s before next profile...", "INFO")
                time.sleep(jitter)

    summary = {
        "order_id": order_id,
        "status": "completed" if (current_order and current_order.get("status") == "completed") else "running",
        "assigned_count": len(assigned_accounts),
        "successful_count": successful_runs,
        "failed_count": failed_runs,
        "session_results": session_results,
        "dry_run": dry_run,
    }

    log(
        f"Order #{order_id} execution batch finished: "
        f"{successful_runs} success, {failed_runs} failed out of {len(assigned_accounts)} sessions.",
        "SUCCESS" if successful_runs > 0 else "WARN",
    )
    return summary
