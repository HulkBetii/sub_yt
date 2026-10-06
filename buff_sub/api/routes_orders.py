# -*- coding: utf-8 -*-
"""
buff_sub.api.routes_orders — Order CRUD, State Transition & Metrics Endpoints
"""
import csv
import io
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, status, Response

from ..database import (
    create_order,
    get_order,
    list_orders,
    delete_order,
    pause_order,
    resume_order,
    get_order_summary,
    get_order_history,
    get_order_export_data,
)
from ..drip_feed import calculate_effective_daily_cap
from .schemas import (
    OrderCreateRequest,
    OrderResponse,
    OrderListResponse,
)

router = APIRouter(prefix="/api/orders", tags=["Orders"])


def _serialize_order(ord_data: dict) -> OrderResponse:
    eff_cap = calculate_effective_daily_cap(ord_data)
    return OrderResponse(
        id=ord_data["id"],
        channel_url=ord_data["channel_url"],
        channel_id=ord_data.get("channel_id"),
        target_subs=ord_data["target_subs"],
        delivered=ord_data.get("delivered", 0),
        daily_cap=ord_data.get("daily_cap", 20),
        effective_daily_cap=eff_cap,
        priority=ord_data.get("priority", 5),
        status=ord_data.get("status", "pending"),
        customer_note=ord_data.get("customer_note"),
        created_at=ord_data.get("created_at"),
        completed_at=ord_data.get("completed_at"),
    )


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def api_create_order(payload: OrderCreateRequest):
    """Create a new subscription delivery order."""
    order_id = create_order(
        channel_url=payload.channel_url,
        target_subs=payload.target_subs,
        daily_cap=payload.daily_cap,
        priority=payload.priority,
        customer_note=payload.customer_note,
    )
    saved = get_order(order_id)
    if not saved:
        raise HTTPException(status_code=500, detail="Failed to retrieve created order")
    return _serialize_order(saved)


@router.get("", response_model=OrderListResponse)
def api_list_orders(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (pending, running, paused, completed)")
):
    """List all orders, optionally filtered by status."""
    orders = list_orders(status=status_filter)
    serialized = [_serialize_order(o) for o in orders]
    return OrderListResponse(total=len(serialized), orders=serialized)


@router.get("/{order_id}", response_model=OrderResponse)
def api_get_order(order_id: int):
    """Get detailed status and metrics for a specific order."""
    order = get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"Order #{order_id} not found")
    return _serialize_order(order)


@router.post("/{order_id}/pause", response_model=OrderResponse)
def api_pause_order(order_id: int):
    """Pause an active order to halt automatic deliveries."""
    order = get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"Order #{order_id} not found")

    pause_order(order_id)
    updated = get_order(order_id)
    return _serialize_order(updated)


@router.post("/{order_id}/resume", response_model=OrderResponse)
def api_resume_order(order_id: int):
    """Resume a paused or pending order to running state."""
    order = get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"Order #{order_id} not found")

    resume_order(order_id)
    updated = get_order(order_id)
    return _serialize_order(updated)


@router.delete("/{order_id}", status_code=status.HTTP_200_OK)
def api_delete_order(order_id: int):
    """Delete an order and its execution history records."""
    order = get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"Order #{order_id} not found")

    deleted = delete_order(order_id)
    return {"status": "deleted", "order_id": order_id, "success": deleted}


@router.get("/{order_id}/summary")
def api_get_order_summary(order_id: int):
    """Get aggregated delivery and engagement statistics for an order."""
    summary = get_order_summary(order_id)
    if not summary:
        raise HTTPException(status_code=404, detail=f"Order #{order_id} not found")
    return summary


@router.get("/{order_id}/history")
def api_get_order_history(
    order_id: int,
    limit: int = Query(100, ge=1, le=1000, description="Max history records to return"),
):
    """Get recent sub execution history records for an order."""
    order = get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"Order #{order_id} not found")

    records = get_order_history(order_id, limit=limit)
    return {"order_id": order_id, "total": len(records), "history": records}


@router.get("/{order_id}/export")
def api_export_order_csv(order_id: int):
    """Export the execution history of an order as a downloadable CSV file."""
    order = get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"Order #{order_id} not found")

    rows = get_order_export_data(order_id)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "history_id",
        "executed_at",
        "account_id",
        "channel_id",
        "sub_success",
        "watch_seconds",
        "did_like",
        "fail_reason",
    ])

    for r in rows:
        writer.writerow([
            r["history_id"],
            r["executed_at"],
            r["account_id"],
            r["channel_id"],
            r["sub_success"],
            r["watch_seconds"],
            r["did_like"],
            r["fail_reason"] or "",
        ])

    csv_data = output.getvalue()
    filename = f"order_{order_id}_export.csv"

    return Response(
        content=csv_data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

