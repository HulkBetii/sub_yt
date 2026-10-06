# -*- coding: utf-8 -*-
"""
Unit test suite for Phase 1 Task 1 (P1.T1): Project Scaffold & Foundation Modules.
Verifies module imports, external dependencies, config integrity, and logging hooks.
"""
import os
import sys
import pytest

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


def test_internal_module_imports():
    """Verify that all core buff_sub modules import cleanly without syntax or missing dependency errors."""
    import buff_sub
    from buff_sub import config
    from buff_sub import logger
    from buff_sub import selenium_utils
    from buff_sub import cdp
    from buff_sub import human_behavior
    from buff_sub import tab_guard
    from buff_sub import gpm_api
    from buff_sub import gpm_bridge

    assert buff_sub.__version__ == "1.0.0"
    assert hasattr(config, "GPM_API_URL")
    assert hasattr(logger, "log")
    assert hasattr(selenium_utils, "safe_quit")
    assert hasattr(cdp, "cdp_setup")
    assert hasattr(human_behavior, "draw_session_archetype")
    assert hasattr(tab_guard, "don_dep_tab_la")
    assert hasattr(gpm_api, "mo_profile_gpm")
    assert hasattr(gpm_bridge, "open_profile_session")


def test_gpm_bridge_all_exports():
    """Verify that 'from buff_sub.gpm_bridge import *' exports all expected functions."""
    import buff_sub.gpm_bridge as bridge

    expected_exports = [
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
    for func_name in expected_exports:
        assert hasattr(bridge, func_name), f"Missing export: {func_name}"
        assert callable(getattr(bridge, func_name)), f"Export is not callable: {func_name}"


def test_external_dependencies():
    """Verify that all declared dependencies in requirements.txt can be imported."""
    import selenium
    import requests
    import fastapi
    import uvicorn
    import apscheduler
    import aiosqlite
    import pydantic
    import humancursor

    assert selenium.__version__ is not None
    assert requests.__version__ is not None
    assert fastapi.__version__ is not None
    assert uvicorn.__version__ is not None
    assert apscheduler.__version__ is not None
    assert aiosqlite.__version__ is not None
    assert pydantic.__version__ is not None
    assert hasattr(humancursor, "WebCursor") or hasattr(humancursor, "SystemCursor")


def test_config_integrity():
    """Verify path configurations and ad-block list."""
    from buff_sub.config import (
        BASE_DIR,
        DATA_DIR,
        LOGS_DIR,
        SHARED_DIR,
        SHARED_DB_PATH,
        LOCAL_DB_PATH,
        LOG_FILE_PATH,
        LOG_FILE,
        DOMAINS_QUANG_CAO,
        GPM_API_URL,
    )

    assert os.path.exists(DATA_DIR), "DATA_DIR must exist"
    assert os.path.exists(LOGS_DIR), "LOGS_DIR must exist"
    assert os.path.exists(SHARED_DIR), "SHARED_DIR must exist"
    assert LOG_FILE == LOG_FILE_PATH
    assert isinstance(DOMAINS_QUANG_CAO, list)
    assert len(DOMAINS_QUANG_CAO) >= 20
    assert "googleadservices.com" in DOMAINS_QUANG_CAO
    assert GPM_API_URL == "http://127.0.0.1:19995"


def test_logger_functionality_and_hooks():
    """Verify logger output, levels, and custom hook dispatch."""
    from buff_sub.logger import log, register_log_hook

    captured_logs = []

    def hook_listener(msg):
        captured_logs.append(msg)

    register_log_hook(hook_listener)

    test_msg = "Kiểm thử tiếng Việt UTF-8 thành công"
    log(test_msg, "SUCCESS")

    assert any(test_msg in log_entry for log_entry in captured_logs), (
        "Log message was not delivered to registered hook"
    )


def test_human_behavior_archetypes():
    """Verify session archetypes and mood drawing."""
    from buff_sub.human_behavior import (
        draw_session_archetype,
        draw_session_mood,
        SessionArchetype,
        SessionMood,
    )

    arch = draw_session_archetype()
    assert isinstance(arch, SessionArchetype)

    mood = draw_session_mood()
    assert isinstance(mood, SessionMood)
    assert 0.0 <= mood.like_click_prob <= 1.0


def test_cdp_bezier_calculation():
    """Verify bezier point calculation in CDP module."""
    from buff_sub.cdp import _bezier_pts

    p0 = (0, 0)
    cp1 = (25, 10)
    cp2 = (75, 90)
    p3 = (100, 100)
    pts = _bezier_pts(p0, cp1, cp2, p3, n_steps=10)
    assert len(pts) == 10
    first_x, first_y = pts[0]
    last_x, last_y = pts[-1]
    assert first_x == 0 and first_y == 0
    assert last_x == 100 and last_y == 100
