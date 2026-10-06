# -*- coding: utf-8 -*-
"""
gpm_bridge.py — High-Level Bridge for GPM Login Profile Lifecycle & CDP Setup
Provides unified session management, anti-detect setup, and resource guardrails for buff-sub-yt.
"""
from typing import Optional, Tuple
from selenium.webdriver.chrome.webdriver import WebDriver

from .logger import log
from .config import GPM_ADDITIONAL_ARGS
from .gpm_api import (
    mo_profile_gpm,
    dong_profile_gpm,
    lay_tat_ca_profiles,
    start_gpm_dialog_watcher,
    tim_gpmdriver,
)
from .cdp import cdp_setup
from .selenium_utils import safe_quit, is_driver_healthy

__all__ = [
    "open_profile_session",
    "close_profile_session",
    "mo_profile_gpm",
    "dong_profile_gpm",
    "lay_tat_ca_profiles",
    "start_gpm_dialog_watcher",
    "tim_gpmdriver",
    "safe_quit",
    "is_driver_healthy",
]


def open_profile_session(
    profile_id: str,
    additional_args: str = GPM_ADDITIONAL_ARGS,
) -> Tuple[Optional[WebDriver], Optional[str]]:
    """
    Launch GPM profile, configure anti-detect CDP hooks, and return (driver, debug_addr).
    Returns (None, None) if launch fails.
    """
    log(f"Starting GPM profile session: {profile_id}", "INFO")
    driver = mo_profile_gpm(profile_id, addination_args=additional_args)
    if driver is None:
        log(f"Failed to open GPM profile {profile_id}", "ERROR")
        return None, None

    debug_addr = ""
    try:
        debug_addr = (driver.capabilities or {}).get("goog:chromeOptions", {}).get("debuggerAddress", "")
    except Exception:
        pass

    # Inject CDP anti-detect and ad-skip scripts
    try:
        cdp_setup(driver)
        log(f"CDP hooks initialized for profile {profile_id}", "SUCCESS")
    except Exception as e:
        log(f"Warning: CDP setup encountered an issue: {e}", "WARN")

    return driver, debug_addr


def close_profile_session(driver: Optional[WebDriver], profile_id: str) -> None:
    """
    Cleanly terminate WebDriver and release GPM profile resources.
    Guarantees no orphan Chromium processes remain in memory.
    """
    log(f"Closing GPM profile session: {profile_id}", "INFO")
    if driver is not None:
        try:
            safe_quit(driver)
        except Exception as e:
            log(f"Error during driver safe_quit: {e}", "WARN")

    try:
        dong_profile_gpm(profile_id)
    except Exception as e:
        log(f"Error during dong_profile_gpm: {e}", "WARN")
