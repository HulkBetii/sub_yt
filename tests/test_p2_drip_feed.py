# -*- coding: utf-8 -*-
"""
tests/test_p2_drip_feed.py — Unit Tests for Organic S-Curve Drip-Feed Logic
Verifies order age calculations, growth multipliers, and effective daily caps.
"""
import pytest
import datetime
from buff_sub.drip_feed import (
    get_order_age_days,
    get_drip_multiplier,
    calculate_effective_daily_cap,
    parse_datetime,
)


def test_parse_datetime():
    """Verify robust parsing of various datetime string formats."""
    dt1 = parse_datetime("2026-10-01 10:00:00")
    assert dt1 == datetime.datetime(2026, 10, 1, 10, 0, 0)

    dt2 = parse_datetime("2026-10-01T15:30:00Z")
    assert dt2 == datetime.datetime(2026, 10, 1, 15, 30, 0)

    dt3 = parse_datetime(None)
    assert dt3 is None


def test_order_age_days_progression():
    """Verify order age calculation across elapsed days."""
    now = datetime.datetime(2026, 10, 10, 12, 0, 0)

    # Created 2 hours ago -> Day 1
    order_day1 = {"created_at": "2026-10-10 10:00:00"}
    assert get_order_age_days(order_day1, current_time=now) == 1

    # Created 3 days ago -> Day 4
    order_day4 = {"created_at": "2026-10-07 10:00:00"}
    assert get_order_age_days(order_day4, current_time=now) == 4

    # Created 10 days ago -> Day 11
    order_day11 = {"created_at": "2026-09-30 10:00:00"}
    assert get_order_age_days(order_day11, current_time=now) == 11


def test_drip_multiplier_curve():
    """Verify S-Curve multiplier thresholds for all phases."""
    # Seeding: Days 1-3
    assert get_drip_multiplier(1) == 0.3
    assert get_drip_multiplier(2) == 0.3
    assert get_drip_multiplier(3) == 0.3

    # Growth: Days 4-7
    assert get_drip_multiplier(4) == 0.6
    assert get_drip_multiplier(7) == 0.6

    # Steady: Days 8-14
    assert get_drip_multiplier(8) == 0.9
    assert get_drip_multiplier(14) == 0.9

    # Mature: Days 15+
    assert get_drip_multiplier(15) == 1.0
    assert get_drip_multiplier(30) == 1.0


def test_calculate_effective_daily_cap_scaling():
    """Verify scaling of base daily cap with minimum 1 sub guarantee."""
    now = datetime.datetime(2026, 10, 10, 12, 0, 0)

    # Base cap 20:
    # Day 1 (30%): 20 * 0.3 = 6
    order = {"daily_cap": 20, "created_at": "2026-10-10 08:00:00"}
    assert calculate_effective_daily_cap(order, current_time=now) == 6

    # Day 5 (60%): 20 * 0.6 = 12
    order_d5 = {"daily_cap": 20, "created_at": "2026-10-06 08:00:00"}
    assert calculate_effective_daily_cap(order_d5, current_time=now) == 12

    # Day 10 (90%): 20 * 0.9 = 18
    order_d10 = {"daily_cap": 20, "created_at": "2026-10-01 08:00:00"}
    assert calculate_effective_daily_cap(order_d10, current_time=now) == 18

    # Day 20 (100%): 20 * 1.0 = 20
    order_d20 = {"daily_cap": 20, "created_at": "2026-09-20 08:00:00"}
    assert calculate_effective_daily_cap(order_d20, current_time=now) == 20


def test_effective_daily_cap_minimum_floor():
    """Verify cap never drops to 0 when daily_cap > 0 (even on small caps like 2)."""
    now = datetime.datetime(2026, 10, 10, 12, 0, 0)

    # 2 * 0.3 = 0.6 -> rounded to 1
    order_small = {"daily_cap": 2, "created_at": "2026-10-10 08:00:00"}
    assert calculate_effective_daily_cap(order_small, current_time=now) == 1

    # Zero base cap should remain 0
    order_zero = {"daily_cap": 0, "created_at": "2026-10-10 08:00:00"}
    assert calculate_effective_daily_cap(order_zero, current_time=now) == 0


def test_effective_daily_cap_disabled_bypass():
    """Verify that disabling drip-feed returns base daily cap directly."""
    order = {"daily_cap": 50, "created_at": "2026-10-10 08:00:00"}
    assert calculate_effective_daily_cap(order, enabled=False) == 50
