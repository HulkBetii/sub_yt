# -*- coding: utf-8 -*-
"""
buff_sub.api.schemas — Pydantic V2 Models for Request and Response Payloads
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ── Orders Schemas ───────────────────────────────────────────────

class OrderCreateRequest(BaseModel):
    channel_url: str = Field(..., description="Target YouTube channel URL or @handle")
    target_subs: int = Field(..., gt=0, description="Total target subscribers requested")
    daily_cap: int = Field(default=20, gt=0, description="Maximum subscribers delivered per day")
    priority: int = Field(default=5, ge=1, le=10, description="Order priority (1: highest, 10: lowest)")
    customer_note: Optional[str] = Field(default=None, description="Optional internal note or order reference")


class OrderResponse(BaseModel):
    id: int
    channel_url: str
    channel_id: Optional[str] = None
    target_subs: int
    delivered: int
    daily_cap: int
    effective_daily_cap: Optional[int] = None
    priority: int
    status: str
    customer_note: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None


class OrderListResponse(BaseModel):
    total: int
    orders: List[OrderResponse]


# ── Scheduler Schemas ────────────────────────────────────────────

class SchedulerStatusResponse(BaseModel):
    is_running: bool
    is_paused: bool
    tick_interval_minutes: int
    active_jobs_count: int
    next_run_time: Optional[str] = None
    last_tick_time: Optional[str] = None
    last_tick_summary: Dict[str, Any] = {}


class TickTriggerResponse(BaseModel):
    status: str
    timestamp: str
    dry_run: bool
    orders_checked: int
    sessions_attempted: int
    successful: int
    details: List[Dict[str, Any]] = []


# ── System & Accounts Schemas ────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "2.0.0"
    service: str = "buff-sub-yt Engine API"


class LogViewerResponse(BaseModel):
    total_lines: int
    lines: List[str]
