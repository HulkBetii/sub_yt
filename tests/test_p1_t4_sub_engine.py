# -*- coding: utf-8 -*-
"""
Unit test suite for Phase 1 Task 4 (P1.T4): Sub Engine (sub_engine.py).
Tests selector parsing, Shadow DOM traversal logic, human click fallback,
ad skipping, account switcher routing, and full session orchestration.
"""
import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from buff_sub.sub_engine import (
    human_click_element,
    find_subscribe_button,
    find_like_button,
    skip_youtube_ads,
    switch_to_account,
    run_sub_session,
    SUBSCRIBE_SELECTORS,
    LIKE_SELECTORS,
    AD_SKIP_SELECTORS,
    ALREADY_SUBSCRIBED_KEYWORDS,
    ALREADY_LIKED_KEYWORDS,
)


def test_subscribe_button_detection_unsubscribed():
    """Verify find_subscribe_button identifies an unsubscribed button correctly."""
    mock_driver = MagicMock()
    mock_btn = MagicMock()
    mock_btn.is_displayed.return_value = True
    mock_btn.text = "Subscribe"
    mock_btn.get_attribute.return_value = "Subscribe to channel"

    mock_driver.find_elements.return_value = [mock_btn]

    btn, already_subbed = find_subscribe_button(mock_driver)
    assert btn == mock_btn
    assert already_subbed is False


def test_subscribe_button_detection_already_subscribed():
    """Verify find_subscribe_button identifies already subscribed state correctly."""
    mock_driver = MagicMock()
    mock_btn = MagicMock()
    mock_btn.is_displayed.return_value = True
    mock_btn.text = "Subscribed"
    mock_btn.get_attribute.return_value = "Subscribed to channel"

    mock_driver.find_elements.return_value = [mock_btn]

    btn, already_subbed = find_subscribe_button(mock_driver)
    assert btn == mock_btn
    assert already_subbed is True


def test_like_button_detection():
    """Verify find_like_button identifies unliked and liked states."""
    mock_driver = MagicMock()
    mock_btn = MagicMock()
    mock_btn.is_displayed.return_value = True
    mock_btn.text = ""
    mock_btn.get_attribute.side_effect = lambda attr: "Like this video" if attr == "aria-label" else "false"

    mock_driver.find_elements.return_value = [mock_btn]

    btn, already_liked = find_like_button(mock_driver)
    assert btn == mock_btn
    assert already_liked is False

    # Now simulate already liked
    mock_btn.get_attribute.side_effect = lambda attr: "Unlike this video" if attr == "aria-label" else "true"
    btn, already_liked = find_like_button(mock_driver)
    assert already_liked is True


def test_ad_skipping_logic():
    """Verify skip_youtube_ads detects and clicks skip buttons."""
    mock_driver = MagicMock()
    mock_btn = MagicMock()
    mock_btn.is_displayed.return_value = True

    mock_driver.find_elements.return_value = [mock_btn]

    assert skip_youtube_ads(mock_driver) is True
    mock_driver.execute_script.assert_called_with("arguments[0].click();", mock_btn)


def test_human_click_fallback_tier():
    """Verify human_click_element falls back gracefully if humancursor is unavailable."""
    mock_driver = MagicMock()
    mock_element = MagicMock()

    # Mock execute_script to return bounding rect for Tier 2 Bézier + CDP
    mock_driver.execute_script.return_value = {"left": 100, "top": 200, "width": 80, "height": 40}

    with patch("buff_sub.sub_engine.bezier_mouse_move") as mock_bezier, \
         patch("buff_sub.sub_engine.cdp_click") as mock_cdp_click:
        result = human_click_element(mock_driver, mock_element)
        assert result is True
        mock_bezier.assert_called_once()
        mock_cdp_click.assert_called_once()


def test_switch_to_account_routing():
    """Verify switch_to_account handles root vs brand accounts."""
    mock_driver = MagicMock()

    # 1. Master Gmail (gmail_root) should not open channel_switcher
    assert switch_to_account(mock_driver, {"account_type": "gmail_root"}) is True
    mock_driver.get.assert_not_called()

    # 2. Brand Account should navigate to channel_switcher
    with patch("buff_sub.sub_engine.safe_get") as mock_safe_get:
        mock_item = MagicMock()
        mock_item.text = "My Brand Channel"
        mock_driver.find_elements.return_value = [mock_item]

        res = switch_to_account(mock_driver, {
            "account_type": "brand_account",
            "switch_name": "My Brand Channel",
        })
        assert res is True
        mock_safe_get.assert_called_once()


@patch("buff_sub.sub_engine.open_profile_session")
@patch("buff_sub.sub_engine.close_profile_session")
@patch("buff_sub.sub_engine.acquire_account_lock")
@patch("buff_sub.sub_engine.get_order")
@patch("buff_sub.sub_engine.get_account")
@patch("buff_sub.sub_engine.warmup_before_sub")
@patch("buff_sub.sub_engine.visit_target_channel_and_watch")
@patch("buff_sub.sub_engine.do_like_if_needed")
@patch("buff_sub.sub_engine.do_subscribe")
@patch("buff_sub.sub_engine.cooldown_browsing")
@patch("buff_sub.sub_engine.update_cooldown")
@patch("buff_sub.sub_engine.log_sub_attempt")
def test_run_sub_session_successful_flow(
    mock_log_sub,
    mock_cooldown,
    mock_cool_browse,
    mock_sub,
    mock_like,
    mock_watch,
    mock_warmup,
    mock_get_acc,
    mock_get_ord,
    mock_lock,
    mock_close,
    mock_open,
):
    """Verify the full orchestration lifecycle of a successful sub session."""
    mock_driver = MagicMock()
    mock_open.return_value = (mock_driver, "127.0.0.1:9222")
    mock_get_ord.return_value = {
        "id": 1,
        "channel_url": "https://www.youtube.com/@TargetChan",
        "channel_id": "@TargetChan",
    }
    mock_get_acc.return_value = {"id": 10, "account_type": "gmail_root"}
    mock_watch.return_value = (150, True)
    mock_like.return_value = True
    mock_sub.return_value = True

    result = run_sub_session(
        gpm_profile_id="prof-123",
        account_id=10,
        order_id=1,
        dry_run=False,
    )

    assert result["sub_success"] is True
    assert result["did_like"] is True
    assert result["watch_seconds"] == 150
    assert result["fail_reason"] is None

    # Verify lifecycle steps executed
    mock_open.assert_called_once_with("prof-123")
    mock_warmup.assert_called_once()
    mock_watch.assert_called_once_with(mock_driver, "https://www.youtube.com/@TargetChan", dry_run=False)
    mock_like.assert_called_once()
    mock_sub.assert_called_once_with(mock_driver)
    mock_cool_browse.assert_called_once_with(mock_driver, dry_run=False)
    mock_close.assert_called_once_with(mock_driver, "prof-123")
    mock_cooldown.assert_called_once_with(10, days=3)
    mock_log_sub.assert_called_once()


@patch("buff_sub.sub_engine.open_profile_session")
@patch("buff_sub.sub_engine.close_profile_session")
@patch("buff_sub.sub_engine.acquire_account_lock")
@patch("buff_sub.sub_engine.get_order")
@patch("buff_sub.sub_engine.get_account")
@patch("buff_sub.sub_engine.warmup_before_sub")
@patch("buff_sub.sub_engine.log_sub_attempt")
def test_run_sub_session_exception_safety(
    mock_log_sub,
    mock_warmup,
    mock_get_acc,
    mock_get_ord,
    mock_lock,
    mock_close,
    mock_open,
):
    """Verify that browser is closed and failure is logged when an exception occurs."""
    mock_driver = MagicMock()
    mock_open.return_value = (mock_driver, "127.0.0.1:9222")
    mock_get_ord.return_value = {
        "id": 1,
        "channel_url": "https://www.youtube.com/@TargetChan",
        "channel_id": "@TargetChan",
    }
    mock_warmup.side_effect = RuntimeError("Network socket disconnected")

    result = run_sub_session(
        gpm_profile_id="prof-crash",
        account_id=15,
        order_id=1,
        dry_run=False,
    )

    assert result["sub_success"] is False
    assert "Network socket disconnected" in result["fail_reason"]
    # Ensure close_profile_session is STILL called
    mock_close.assert_called_once_with(mock_driver, "prof-crash")
    # Ensure failure is logged to DB
    mock_log_sub.assert_called_once()
    _, kwargs = mock_log_sub.call_args
    assert kwargs["sub_success"] is False


@patch("buff_sub.sub_engine.open_profile_session")
@patch("buff_sub.sub_engine.close_profile_session")
@patch("buff_sub.sub_engine.acquire_account_lock")
@patch("buff_sub.sub_engine.get_order")
@patch("buff_sub.sub_engine.get_account")
@patch("buff_sub.sub_engine.warmup_before_sub")
@patch("buff_sub.sub_engine.visit_target_channel_and_watch")
@patch("buff_sub.sub_engine.cooldown_browsing")
@patch("buff_sub.sub_engine.update_cooldown")
@patch("buff_sub.sub_engine.log_sub_attempt")
def test_run_sub_session_dry_run_mode(
    mock_log_sub,
    mock_cooldown,
    mock_cool_browse,
    mock_watch,
    mock_warmup,
    mock_get_acc,
    mock_get_ord,
    mock_lock,
    mock_close,
    mock_open,
):
    """Verify dry_run mode does not modify DB or cooldown."""
    mock_driver = MagicMock()
    mock_open.return_value = (mock_driver, "127.0.0.1:9222")
    mock_get_ord.return_value = {
        "id": 2,
        "channel_url": "https://www.youtube.com/@DryRunChan",
        "channel_id": "@DryRunChan",
    }
    mock_watch.return_value = (90, True)

    result = run_sub_session(
        gpm_profile_id="prof-dry",
        account_id=20,
        order_id=2,
        dry_run=True,
    )

    assert result["sub_success"] is True
    assert result["dry_run"] is True
    # Cooldown and sub history should NOT be written in dry run
    mock_cooldown.assert_not_called()
    mock_log_sub.assert_not_called()
    mock_close.assert_called_once_with(mock_driver, "prof-dry")
