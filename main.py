#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Main Entry Point for buff-sub-yt Engine
Unified Command-Line Interface (CLI), FastAPI Server & Autonomous Daemon.
"""
import sys
import time
import argparse

# UTF-8 encoding safeguard
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from buff_sub.logger import log
from buff_sub.config import (
    GPM_API_URL,
    SHARED_DB_PATH,
    LOCAL_DB_PATH,
    API_HOST,
    API_PORT,
    SCHEDULER_TICK_INTERVAL_MINUTES,
)
from buff_sub.database import (
    create_order,
    list_orders,
    pause_order,
    resume_order,
)
from buff_sub.account_pool import get_pool_status
from buff_sub.order_manager import process_order
from buff_sub.scheduler import (
    start_scheduler,
    stop_scheduler,
    trigger_tick_now,
    get_scheduler_status,
)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="buff-sub-yt: Enterprise Organic YouTube Subscription Engine & Autonomous Scheduler"
    )
    # Order management
    parser.add_argument("--list-orders", action="store_true", help="List all subscription orders")
    parser.add_argument("--create-order", action="store_true", help="Create a new subscription order")
    parser.add_argument("--channel", type=str, help="Target YouTube Channel URL (e.g. https://www.youtube.com/@Channel)")
    parser.add_argument("--target", type=int, default=100, help="Target subscribers count (default: 100)")
    parser.add_argument("--daily-cap", type=int, default=20, help="Maximum subscriptions per day (default: 20)")
    parser.add_argument("--order-id", type=int, help="Order ID to process")
    parser.add_argument("--pause-order", type=int, help="Pause a specific order ID")
    parser.add_argument("--resume-order", type=int, help="Resume a specific order ID")
    parser.add_argument("--max-subs", type=int, help="Maximum number of accounts/subs to process in this run")
    parser.add_argument("--dry-run", action="store_true", help="Simulate session without clicking subscribe")
    parser.add_argument("--status", action="store_true", help="Display account pool status and health")

    # Autonomous Scheduler & REST API
    parser.add_argument("--serve", action="store_true", help="Start FastAPI REST API server with integrated scheduler")
    parser.add_argument("--host", type=str, default=API_HOST, help=f"API server bind host (default: {API_HOST})")
    parser.add_argument("--port", type=int, default=API_PORT, help=f"API server bind port (default: {API_PORT})")
    parser.add_argument("--scheduler-daemon", action="store_true", help="Run background scheduler worker in standalone daemon mode")
    parser.add_argument("--tick", action="store_true", help="Manually invoke a routine scheduler tick immediately")

    return parser.parse_args()


def main():
    args = parse_arguments()
    log("=== buff-sub-yt Engine CLI ===", "INFO")
    log(f"Shared DB: {SHARED_DB_PATH}", "INFO")
    log(f"Local DB:  {LOCAL_DB_PATH}", "INFO")
    log(f"GPM API:   {GPM_API_URL}", "INFO")

    # 1. Start FastAPI REST Server
    if args.serve:
        log(f"Starting buff-sub-yt REST API Service on http://{args.host}:{args.port}...", "INFO")
        try:
            import uvicorn
            uvicorn.run("buff_sub.api.app:app", host=args.host, port=args.port, reload=False)
        except KeyboardInterrupt:
            log("API Service interrupted by user. Shutting down cleanly.", "INFO")
        except Exception as e:
            log(f"Failed to run API server: {e}", "ERROR")
        return

    # 2. Standalone Scheduler Daemon
    if args.scheduler_daemon:
        log("Starting autonomous scheduler in standalone daemon mode...", "INFO")
        start_scheduler(tick_minutes=SCHEDULER_TICK_INTERVAL_MINUTES, dry_run=args.dry_run)
        log("Scheduler daemon is running. Press Ctrl+C to stop.", "SUCCESS")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            log("Scheduler daemon stopped by user.", "INFO")
            stop_scheduler()
        return

    # 3. Manual Routine Tick
    if args.tick:
        log(f"Executing manual routine tick (Dry-run: {args.dry_run})...", "INFO")
        res = trigger_tick_now(dry_run=args.dry_run)
        print("\n" + "=" * 60)
        print("             SCHEDULER ROUTINE TICK REPORT             ")
        print("=" * 60)
        print(f"  Execution Status:     {res.get('status', '').upper()}")
        print(f"  Timestamp:            {res.get('timestamp')}")
        print(f"  Dry-run Mode:         {res.get('dry_run')}")
        print(f"  Orders Evaluated:     {res.get('orders_checked', 0)}")
        print(f"  Sessions Attempted:   {res.get('sessions_attempted', 0)}")
        print(f"  Successful Sessions:  {res.get('successful', 0)}")
        details = res.get("details", [])
        if details:
            print("-" * 60)
            print(f"  {'ORDER ID':<10} {'ACTION':<12} {'RESULT / REASON'}")
            for d in details:
                act = d.get("action", "")
                rs = d.get("reason") or f"status: {d.get('status')}, ok: {d.get('successful')}"
                print(f"  #{d.get('order_id'):<9} {act:<12} {rs}")
        print("=" * 60 + "\n")
        return

    # 4. Account Pool Health
    if args.status:
        log("Inspecting shared account pool...", "INFO")
        try:
            status = get_pool_status()
            print("\n" + "=" * 50)
            print("       ACCOUNT POOL STATUS & HEALTH       ")
            print("=" * 50)
            print(f"  GPM Profiles Total:      {status['total_gpm_profiles']} (Active: {status['active_gpm_profiles']})")
            print(f"  Sub Accounts Total:      {status['total_sub_accounts']}")
            print(f"    - Gmail Root (Tier 1): {status['gmail_root_accounts']}")
            print(f"    - Brand Accs (Tier 2): {status['brand_accounts']}")
            print("-" * 50)
            print(f"  Ready Accounts:          {status['ready_accounts']}")
            print(f"  Warming Accounts:        {status['warming_accounts']}")
            print(f"  Cold Accounts:           {status['cold_accounts']}")
            print(f"  Suspended Accounts:      {status['suspended_accounts']}")
            print("-" * 50)
            print(f"  Currently Locked:        {status['active_locks']}")
            print(f"  On Cooldown:             {status['on_cooldown']}")
            print(f"  AVAILABLE FOR WORK NOW:  {status['available_now']}")
            print("=" * 50 + "\n")
            log("Account pool inspection complete.", "SUCCESS")
        except Exception as e:
            log(f"Failed to inspect account pool: {e}", "ERROR")
        return

    # 5. List Orders
    if args.list_orders:
        log("Listing orders from local database...", "INFO")
        orders = list_orders()
        if not orders:
            log("No orders found in database.", "WARN")
            return
        print(f"\n{'ID':<5} {'CHANNEL':<25} {'TARGET':<8} {'DELIVERED':<10} {'STATUS':<12} {'DAILY CAP':<10}")
        print("-" * 75)
        for o in orders:
            ch = o.get("channel_id") or o.get("channel_url", "")
            print(f"{o['id']:<5} {ch:<25} {o['target_subs']:<8} {o['delivered']:<10} {o['status']:<12} {o['daily_cap']:<10}")
        print()
        return

    # 6. Pause Order
    if args.pause_order:
        ok = pause_order(args.pause_order)
        if ok:
            log(f"Order #{args.pause_order} is now PAUSED.", "SUCCESS")
        else:
            log(f"Failed to pause Order #{args.pause_order}.", "ERROR")
        return

    # 7. Resume Order
    if args.resume_order:
        ok = resume_order(args.resume_order)
        if ok:
            log(f"Order #{args.resume_order} is now RUNNING.", "SUCCESS")
        else:
            log(f"Failed to resume Order #{args.resume_order}.", "ERROR")
        return

    # 8. Create Order
    if args.create_order:
        if not args.channel:
            log("Error: --channel argument is required when creating an order.", "ERROR")
            sys.exit(1)
        order_id = create_order(
            channel_url=args.channel,
            target_subs=args.target,
            daily_cap=args.daily_cap,
        )
        log(f"Order #{order_id} created successfully for {args.channel}", "SUCCESS")
        return

    # 9. Process Single Order
    if args.order_id:
        log(f"Processing Order ID: {args.order_id} (Dry-run: {args.dry_run}, Max subs: {args.max_subs})", "INFO")
        summary = process_order(
            order_id=args.order_id,
            max_subs=args.max_subs,
            dry_run=args.dry_run,
        )
        print("\n" + "=" * 60)
        print("                ORDER EXECUTION REPORT                 ")
        print("=" * 60)
        print(f"  Order ID:             #{summary.get('order_id')}")
        print(f"  Execution Status:     {str(summary.get('status', 'unknown')).upper()}")
        print(f"  Dry-run Mode:         {summary.get('dry_run', False)}")
        print(f"  Accounts Assigned:    {summary.get('assigned_count', 0)}")
        print(f"  Successful Sessions:  {summary.get('successful_count', 0)}")
        print(f"  Failed Sessions:      {summary.get('failed_count', 0)}")
        if summary.get("message"):
            print(f"  Notice:               {summary['message']}")
        print("-" * 60)
        sessions = summary.get("session_results", [])
        if sessions:
            print(f"  {'ACC ID':<8} {'STATUS':<12} {'LIKE':<8} {'WATCH TIME':<12} {'NOTE'}")
            for s in sessions:
                st = "SUCCESS" if s.get("sub_success") else "FAILED"
                lk = "YES" if s.get("did_like") else "NO"
                wt = f"{s.get('watch_seconds', 0)}s"
                nt = s.get("fail_reason") or "OK"
                print(f"  {s.get('account_id'):<8} {st:<12} {lk:<8} {wt:<12} {nt}")
        print("=" * 60 + "\n")
        return

    # If no flags passed, show help
    log("No actionable flags provided. Use --help for command options.", "WARN")


if __name__ == "__main__":
    main()
