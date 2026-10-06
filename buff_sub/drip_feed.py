# -*- coding: utf-8 -*-
"""
drip_feed.py — Organic S-Curve Growth Modeling for YouTube Subscriptions
Simulates natural channel discovery and audience ramp-up to prevent
algorithmic anomaly flags and subscription purge cascades.
"""
from typing import Dict, Any, Optional
import datetime

from .logger import log
from .config import DRIP_FEED_ENABLED


def parse_datetime(dt_val: Any) -> Optional[datetime.datetime]:
    """Parse various datetime representations into a timezone-naive UTC datetime."""
    if not dt_val:
        return None
    if isinstance(dt_val, datetime.datetime):
        return dt_val.replace(tzinfo=None) if dt_val.tzinfo else dt_val

    dt_str = str(dt_val).strip()
    # Try ISO formats and standard SQLite timestamps
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.datetime.strptime(dt_str.split("+")[0].split("Z")[0], fmt)
        except ValueError:
            pass
    return None


def get_order_age_days(order: Dict[str, Any], current_time: Optional[datetime.datetime] = None) -> int:
    """
    Calculate the age of an order in days since creation.
    Day 1 represents the first 24 hours of creation.
    Returns: int >= 1
    """
    now = current_time or datetime.datetime.utcnow()
    created_raw = order.get("created_at")
    created_dt = parse_datetime(created_raw)

    if not created_dt:
        return 1

    diff = now - created_dt
    days = diff.total_seconds() / 86400.0

    # 0 to 24h is day 1, 24h to 48h is day 2, etc.
    return max(1, int(days) + 1)


def get_drip_multiplier(age_days: int) -> float:
    """
    Returns the target daily capacity multiplier according to natural S-Curve:
      - Days 1–3  (Seeding phase): 30% capacity
      - Days 4–7  (Growth phase):  60% capacity
      - Days 8–14 (Steady phase):  90% capacity
      - Days 15+  (Mature phase): 100% capacity
    """
    if age_days <= 3:
        return 0.3
    elif age_days <= 7:
        return 0.6
    elif age_days <= 14:
        return 0.9
    else:
        return 1.0


def calculate_effective_daily_cap(
    order: Dict[str, Any],
    current_time: Optional[datetime.datetime] = None,
    enabled: bool = DRIP_FEED_ENABLED,
) -> int:
    """
    Compute effective daily subscription cap for an order on the current day.
    Guarantees at least 1 sub/day if base daily_cap > 0 to avoid stalling.
    If drip-feed is disabled, returns base daily_cap directly.
    """
    raw_cap = order.get("daily_cap")
    base_cap = int(raw_cap) if raw_cap is not None else 20
    if base_cap <= 0:
        return 0

    if not enabled:
        return base_cap

    age_days = get_order_age_days(order, current_time=current_time)
    multiplier = get_drip_multiplier(age_days)
    calculated = int(round(base_cap * multiplier))

    effective = max(1, calculated)
    return effective
