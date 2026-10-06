# -*- coding: utf-8 -*-
"""
buff_sub.api.routes_system — System Overview, Account Pool Diagnostics & Logs
"""
import os
from typing import Dict, Any, List
from fastapi import APIRouter, Query

from ..database import get_system_stats
from ..account_pool import get_pool_status, list_sub_accounts
from ..config import LOG_FILE_PATH
from .schemas import HealthResponse, LogViewerResponse

router = APIRouter(prefix="/api", tags=["System"])


@router.get("/health", response_model=HealthResponse)
def api_health():
    """Health check endpoint to verify API service uptime."""
    return HealthResponse()


@router.get("/stats")
def api_system_stats() -> Dict[str, Any]:
    """Retrieve consolidated system health, orders progress, and account pool metrics."""
    return get_system_stats()


@router.get("/accounts")
def api_account_pool_status() -> Dict[str, Any]:
    """Inspect active 500-account pool status, ready counts, locks, and cooldowns."""
    return get_pool_status()


@router.get("/accounts/list")
def api_list_sub_accounts(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    tier: str = Query(default=None),
    status: str = Query(default=None),
) -> Dict[str, Any]:
    """List detailed sub accounts in the pool with filters for tier, status, locks and cooldowns."""
    return list_sub_accounts(limit=limit, offset=offset, tier=tier, warmup_status=status)



@router.get("/logs", response_model=LogViewerResponse)
def api_get_logs(
    limit: int = Query(default=100, ge=10, le=1000, description="Number of recent log lines to fetch")
):
    """Fetch recent execution log entries for real-time monitoring."""
    if not os.path.exists(LOG_FILE_PATH):
        return LogViewerResponse(total_lines=0, lines=[])

    try:
        with open(LOG_FILE_PATH, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        selected = [line.rstrip() for line in all_lines[-limit:]]
        return LogViewerResponse(total_lines=len(selected), lines=selected)
    except Exception as e:
        return LogViewerResponse(total_lines=1, lines=[f"Error reading log file: {e}"])
