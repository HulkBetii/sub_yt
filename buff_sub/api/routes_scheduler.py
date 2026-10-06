# -*- coding: utf-8 -*-
"""
buff_sub.api.routes_scheduler — Autonomous Scheduler Control & Trigger Endpoints
"""
from fastapi import APIRouter, Query, HTTPException

from ..scheduler import (
    start_scheduler,
    stop_scheduler,
    pause_scheduler,
    resume_scheduler,
    get_scheduler_status,
    trigger_tick_now,
    trigger_warmup_tick_now,
    trigger_maintenance_tick_now,
)
from .schemas import (
    SchedulerStatusResponse,
    TickTriggerResponse,
    WarmupTriggerResponse,
)

router = APIRouter(prefix="/api/scheduler", tags=["Scheduler"])


@router.get("/status", response_model=SchedulerStatusResponse)
def api_scheduler_status():
    """Retrieve runtime state and execution metrics of the autonomous scheduler."""
    return get_scheduler_status()


@router.post("/start", response_model=SchedulerStatusResponse)
def api_start_scheduler(
    tick_minutes: int = Query(default=15, ge=1, le=1440, description="Routine check interval in minutes")
):
    """Start the background routine scheduler."""
    start_scheduler(tick_minutes=tick_minutes)
    return get_scheduler_status()


@router.post("/stop", response_model=SchedulerStatusResponse)
def api_stop_scheduler():
    """Stop the background routine scheduler."""
    stop_scheduler()
    return get_scheduler_status()


@router.post("/pause", response_model=SchedulerStatusResponse)
def api_pause_scheduler():
    """Temporarily pause routine tick execution."""
    pause_scheduler()
    return get_scheduler_status()


@router.post("/resume", response_model=SchedulerStatusResponse)
def api_resume_scheduler():
    """Resume routine tick execution."""
    resume_scheduler()
    return get_scheduler_status()


@router.post("/tick", response_model=TickTriggerResponse)
def api_trigger_tick(
    dry_run: bool = Query(default=False, description="Simulate sub interactions without clicking")
):
    """Manually invoke a routine drip-feed tick immediately."""
    result = trigger_tick_now(dry_run=dry_run)
    return TickTriggerResponse(
        status=result.get("status", "completed"),
        timestamp=result.get("timestamp", ""),
        dry_run=result.get("dry_run", dry_run),
        orders_checked=result.get("orders_checked", 0),
        sessions_attempted=result.get("sessions_attempted", 0),
        successful=result.get("successful", 0),
        details=result.get("details", []),
    )


@router.post("/warmup-tick", response_model=WarmupTriggerResponse)
def api_trigger_warmup_tick(
    dry_run: bool = Query(default=False, description="Simulate warmup sessions without opening browser"),
    duration_minutes: int = Query(default=5, ge=1, le=30, description="Warmup duration per account in minutes")
):
    """Manually invoke an autonomous warmup routine tick immediately."""
    result = trigger_warmup_tick_now(dry_run=dry_run, duration_minutes=duration_minutes)
    return WarmupTriggerResponse(
        status=result.get("status", "completed"),
        timestamp=result.get("timestamp", ""),
        dry_run=result.get("dry_run", dry_run),
        accounts_processed=result.get("accounts_processed", 0),
        successful=result.get("successful", 0),
        details=result.get("details", []),
    )


@router.post("/maintenance-tick")
def api_trigger_maintenance_tick():
    """Manually invoke periodic maintenance (clean expired locks and stale state)."""
    return trigger_maintenance_tick_now()

