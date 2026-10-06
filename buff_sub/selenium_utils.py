# -*- coding: utf-8 -*-
"""
Selenium utilities — timeout protection và helpers cấp thấp.
Không chứa business logic.
"""
import socket
import time
from contextlib import contextmanager

from selenium.common.exceptions import InvalidSessionIdException, WebDriverException
from urllib3.exceptions import (
    MaxRetryError,
    NewConnectionError,
    ProtocolError,
    ReadTimeoutError,
)
from urllib3.util.timeout import Timeout


DEFAULT_COMMAND_TIMEOUT = 15
PAGE_LOAD_TIMEOUT_GRACE = 10
_DRIVER_UNHEALTHY_ATTR = "_nuoi_kenh_unhealthy"
_DRIVER_FAILURE_ATTR = "_nuoi_kenh_failure"
_DRIVER_EXECUTE_WRAPPED_ATTR = "_nuoi_kenh_execute_wrapped"
_FAILED = object()

# ── Timeout toàn cục ─────────────────────────────────────────────
# Page navigation gets a dedicated longer timeout in safe_get().
socket.setdefaulttimeout(DEFAULT_COMMAND_TIMEOUT)

try:
    from selenium.webdriver.remote.remote_connection import RemoteConnection
    RemoteConnection._timeout = DEFAULT_COMMAND_TIMEOUT
except Exception:
    pass


def mark_driver_unhealthy(driver, reason: str = "") -> None:
    try:
        setattr(driver, _DRIVER_UNHEALTHY_ATTR, True)
        if reason:
            setattr(driver, _DRIVER_FAILURE_ATTR, reason[:240])
    except Exception:
        pass


def is_driver_healthy(driver) -> bool:
    return driver is not None and not getattr(driver, _DRIVER_UNHEALTHY_ATTR, False)


def driver_failure_reason(driver) -> str:
    return getattr(driver, _DRIVER_FAILURE_ATTR, "") or "unknown transport failure"


def _is_fatal_driver_error(error: Exception) -> bool:
    if isinstance(error, (
        InvalidSessionIdException,
        ReadTimeoutError,
        ProtocolError,
        NewConnectionError,
        MaxRetryError,
    )):
        return True

    message = str(error).lower()
    fatal_markers = (
        "read timed out",
        "max retries exceeded",
        "connection refused",
        "connection aborted",
        "remote end closed connection",
        "chrome not reachable",
        "not connected to devtools",
        "disconnected: not connected",
        "invalid session id",
    )
    return isinstance(error, WebDriverException) and any(
        marker in message for marker in fatal_markers
    )


def _timeout_value(seconds: float) -> Timeout:
    return Timeout(connect=min(5, seconds), read=seconds)


def _connection_pools(driver) -> list:
    try:
        pool_manager = driver.command_executor._conn
        if hasattr(pool_manager, "pools"):
            return list(pool_manager.pools.values())
    except Exception:
        pass
    return []


def _set_transport_timeout(driver, timeout_value):
    client_config = driver.command_executor.client_config
    client_config.timeout = timeout_value

    pool_manager = driver.command_executor._conn
    if hasattr(pool_manager, "connection_pool_kw"):
        pool_manager.connection_pool_kw["timeout"] = timeout_value
    for pool in _connection_pools(driver):
        if hasattr(pool, "timeout"):
            pool.timeout = timeout_value


def _disable_transport_retries(driver) -> None:
    """WebDriver commands are not idempotent; never retry them automatically."""
    pool_manager = driver.command_executor._conn
    if hasattr(pool_manager, "connection_pool_kw"):
        pool_manager.connection_pool_kw["retries"] = False
    for pool in _connection_pools(driver):
        if hasattr(pool, "retries"):
            pool.retries = False


@contextmanager
def _temporary_transport_timeout(driver, seconds: float):
    client_config = driver.command_executor.client_config
    original_client_timeout = client_config.timeout
    pool_manager = driver.command_executor._conn
    original_pool_timeout = None
    if hasattr(pool_manager, "connection_pool_kw"):
        original_pool_timeout = pool_manager.connection_pool_kw.get("timeout")
    pools = _connection_pools(driver)
    original_pool_timeouts = [
        (pool, getattr(pool, "timeout", None)) for pool in pools
    ]

    _set_transport_timeout(driver, _timeout_value(seconds))
    try:
        yield
    finally:
        client_config.timeout = original_client_timeout
        if hasattr(pool_manager, "connection_pool_kw"):
            pool_manager.connection_pool_kw["timeout"] = original_pool_timeout
        for pool, original_timeout in original_pool_timeouts:
            try:
                pool.timeout = original_timeout
            except Exception:
                pass


def configure_driver_transport(
    driver,
    command_timeout: int = DEFAULT_COMMAND_TIMEOUT,
) -> None:
    """Apply bounded command transport and mark fatal failures centrally."""
    setattr(driver, _DRIVER_UNHEALTHY_ATTR, False)
    setattr(driver, _DRIVER_FAILURE_ATTR, "")
    _set_transport_timeout(driver, _timeout_value(command_timeout))
    _disable_transport_retries(driver)

    if getattr(driver, _DRIVER_EXECUTE_WRAPPED_ATTR, False):
        return

    original_execute = driver.execute

    def guarded_execute(command, params=None):
        if not is_driver_healthy(driver):
            raise WebDriverException("Driver transport is marked unhealthy")
        try:
            return original_execute(command, params)
        except Exception as error:
            if _is_fatal_driver_error(error):
                mark_driver_unhealthy(
                    driver,
                    f"{command}: {type(error).__name__}: {str(error)}",
                )
            raise

    driver.execute = guarded_execute
    setattr(driver, _DRIVER_EXECUTE_WRAPPED_ATTR, True)


def selenium_call(func, *args, driver, timeout=25, default=None):
    """
    Run one WebDriver command with a real urllib3 transport timeout.

    No worker thread is used. A transport timeout marks the driver unhealthy,
    preventing later commands from building a queue behind a frozen GPMDriver.
    """
    if not is_driver_healthy(driver):
        return default
    try:
        with _temporary_transport_timeout(driver, timeout):
            return func(*args)
    except Exception as error:
        if _is_fatal_driver_error(error):
            if is_driver_healthy(driver):
                mark_driver_unhealthy(
                    driver,
                    f"{type(error).__name__}: {str(error)}",
                )
            return default
        raise


def _cho_trang_load(driver, timeout=40):
    """Chờ trang load xong dùng document.readyState."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and is_driver_healthy(driver):
        remaining = deadline - time.monotonic()
        try:
            state = selenium_call(
                lambda: driver.execute_script("return document.readyState"),
                driver=driver,
                timeout=max(1, min(5, remaining)),
                default=None,
            )
        except Exception:
            return False
        if state == "complete":
            return True
        if not is_driver_healthy(driver):
            return False
        time.sleep(0.5)
    return False


def _is_content_tab_url(url: str) -> bool:
    if not url:
        return False
    url_lower = url.lower()
    if url_lower.startswith(("chrome-extension://", "data:", "devtools://")):
        return False
    return url_lower.startswith((
        "http://",
        "https://",
        "about:blank",
        "about:newtab",
        "about:home",
        "chrome://new-tab-page",
        "chrome://newtab",
    ))


def focus_content_tab(
    driver,
    preferred_handle: str = None,
    create_if_missing: bool = True,
) -> str | None:
    """Focus a navigable browser tab, never an extension background page."""
    if not is_driver_healthy(driver):
        return None

    handles = safe_window_handles(driver)
    if not handles:
        return None

    current_handle = selenium_call(
        lambda: driver.current_window_handle,
        driver=driver,
        timeout=5,
        default=None,
    )
    candidates = []
    for handle in (preferred_handle, current_handle, *handles):
        if handle and handle in handles and handle not in candidates:
            candidates.append(handle)

    for handle in candidates:
        url = selenium_call(
            lambda handle=handle: (
                driver.switch_to.window(handle),
                driver.current_url,
            )[1],
            driver=driver,
            timeout=8,
            default=None,
        )
        if _is_content_tab_url(url):
            return handle

    if not create_if_missing:
        return None

    new_handle = selenium_call(
        lambda: (
            driver.switch_to.new_window("tab"),
            driver.current_window_handle,
        )[1],
        driver=driver,
        timeout=10,
        default=None,
    )
    return new_handle


def safe_get(driver, url: str, timeout: int = 45) -> bool:
    """Navigate with separate page-load and HTTP transport deadlines."""
    if not is_driver_healthy(driver):
        return False

    target_handle = focus_content_tab(driver)
    if not target_handle:
        return False

    page_timeout_set = selenium_call(
        lambda: driver.set_page_load_timeout(timeout),
        driver=driver,
        timeout=5,
        default=_FAILED,
    )
    if page_timeout_set is _FAILED:
        return False

    try:
        result = selenium_call(
            lambda: driver.get(url),
            driver=driver,
            timeout=timeout + PAGE_LOAD_TIMEOUT_GRACE,
            default=_FAILED,
        )
        if result is _FAILED:
            return False
        return focus_content_tab(
            driver,
            preferred_handle=target_handle,
            create_if_missing=False,
        ) == target_handle
    except Exception:
        return False
    finally:
        if is_driver_healthy(driver):
            selenium_call(
                lambda: driver.set_page_load_timeout(60),
                driver=driver,
                timeout=5,
                default=None,
            )


def safe_window_handles(driver, default=None):
    """Return window handles without leaving a blocked command behind."""
    fallback = default if default is not None else set()
    result = selenium_call(
        lambda: set(driver.window_handles),
        driver=driver,
        timeout=10,
        default=_FAILED,
    )
    return fallback if result is _FAILED else result


def safe_quit(driver, timeout: int = 10) -> bool:
    """Quit only while transport is usable; GPM API handles broken sessions."""
    if not is_driver_healthy(driver):
        return False
    try:
        result = selenium_call(
            lambda: driver.quit(),
            driver=driver,
            timeout=timeout,
            default=_FAILED,
        )
        return result is not _FAILED
    except Exception:
        return False
