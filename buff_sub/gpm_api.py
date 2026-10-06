# -*- coding: utf-8 -*-
"""GPM Login API — khởi động/đóng profile, kết nối Selenium."""
import os
import re
import time
import ctypes
import ctypes.wintypes
import threading
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService

from .config import GPM_API_URL, GPM_BROWSER_DIR
from .logger import log
from .selenium_utils import (
    configure_driver_transport,
    safe_get,
    selenium_call,
)


# ── Auto-dismiss "Timeout (APP)" dialog ──────────────────────────

_user32 = ctypes.windll.user32
_BM_CLICK = 0x00F5
_EnumWinProc   = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
_EnumChildProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)


def _get_win_text(hwnd: int) -> str:
    n = _user32.GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    _user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _scan_and_dismiss() -> None:
    """Quét tất cả cửa sổ, tìm dialog có chứa 'Timeout' và click OK."""
    dismissed: list[int] = []

    def on_win(hwnd, _):
        if not _user32.IsWindowVisible(hwnd):
            return True

        has_timeout = [False]

        def on_child_check(ch, _):
            if "Timeout" in _get_win_text(ch) or "timeout" in _get_win_text(ch):
                has_timeout[0] = True
                return False
            return True

        _user32.EnumChildWindows(hwnd, _EnumChildProc(on_child_check), 0)

        if not has_timeout[0]:
            return True

        def on_child_click(ch, _):
            if _get_win_text(ch) in ("OK", "Ok"):
                _user32.SendMessageW(ch, _BM_CLICK, 0, 0)
                dismissed.append(hwnd)
                log(f"[GPM] ✅ Đã tự động bấm OK trên dialog Timeout")
                return False
            return True

        _user32.EnumChildWindows(hwnd, _EnumChildProc(on_child_click), 0)
        return True

    _user32.EnumWindows(_EnumWinProc(on_win), 0)


def _dialog_watcher_loop() -> None:
    while True:
        try:
            _scan_and_dismiss()
        except Exception:
            pass
        time.sleep(0.8)


def start_gpm_dialog_watcher() -> None:
    """Khởi động background thread tự động đóng dialog Timeout (APP)."""
    t = threading.Thread(target=_dialog_watcher_loop, daemon=True, name="gpm-dialog-watcher")
    t.start()
    log("[GPM] 🔄 Dialog watcher đã khởi động (tự động bấm OK khi Timeout)")


# ── Tìm gpmdriver ────────────────────────────────────────────────

def tim_gpmdriver() -> str | None:
    """Tìm gpmdriver.exe trong thư mục GPM."""
    if not os.path.exists(GPM_BROWSER_DIR):
        return None
    prefixes     = ["gpm_browser_chromium_core", "gpm_browser_chrome_core"]
    driver_names = ["gpmdriver.exe", "chromedriver.exe"]
    for prefix in prefixes:
        folders = sorted(
            [f for f in os.listdir(GPM_BROWSER_DIR) if f.startswith(prefix)],
            reverse=True
        )
        for folder in folders:
            for drv in driver_names:
                p = os.path.join(GPM_BROWSER_DIR, folder, drv)
                if os.path.exists(p):
                    return p
    return None


# ── GPM Profile API ───────────────────────────────────────────────

# ── GPM Profile API v2 ───────────────────────────────────────────

def lay_tat_ca_profiles(page: int = 1, per_page: int = 10000) -> list[dict]:
    """Lấy danh sách profiles từ GPM-Login qua API v2."""
    try:
        resp = requests.get(
            f"{GPM_API_URL}/v2/profiles",
            params={"page": page, "per_page": per_page},
            timeout=10
        )
        data = resp.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        log(f"❌ Không lấy được profiles: {e}")
        return []


def dong_profile_gpm(profile_id: str) -> bool:
    """Đóng profile GPM theo profile_id."""
    try:
        resp = requests.get(
            f"{GPM_API_URL}/v2/stop",
            params={"profile_id": profile_id},
            timeout=10
        )
        return resp.status_code == 200 and "OK" in resp.text
    except Exception:
        return False


def tao_profile_gpm(
    name: str,
    proxy: str = "",
    group: str = "All",
    canvas: str = "off",
    font: str = "on",
    webrtc: str = "on",
    user_agent: str = "",
    save_type: str = "local",
) -> dict | None:
    """
    Tạo profile mới trên GPM-Login (API v2).
    Trả về dict: {"status": bool, "profile_id": str} hoặc None nếu lỗi.
    """
    try:
        params = {
            "name": name,
            "group": group,
            "canvas": canvas,
            "font": font,
            "webrtc": webrtc,
            "save_type": save_type,
        }
        if proxy:
            params["proxy"] = proxy
        if user_agent:
            params["user_agent"] = user_agent

        resp = requests.get(f"{GPM_API_URL}/v2/create", params=params, timeout=15)
        data = resp.json()
        if isinstance(data, dict) and data.get("status"):
            log(f"  ✅ Đã tạo profile [{name}] (id: {data.get('profile_id')})")
            return data
        log(f"  ❌ Tạo profile thất bại: {data}")
        return None
    except Exception as e:
        log(f"  ❌ Lỗi khi tạo profile: {e}")
        return None


def cap_nhat_profile_gpm(
    profile_id: str,
    name: str = None,
    proxy: str = None,
    note: str = None,
) -> bool:
    """Cập nhật thông tin profile (name, proxy, note)."""
    try:
        params = {"id": profile_id}
        if name is not None:
            params["name"] = name
        if proxy is not None:
            params["proxy"] = proxy
        if note is not None:
            params["note"] = note

        resp = requests.get(f"{GPM_API_URL}/v2/update", params=params, timeout=10)
        return resp.text.strip().lower() == "true"
    except Exception as e:
        log(f"  ❌ Lỗi khi cập nhật profile: {e}")
        return False


def cap_nhat_proxy_gpm(profile_id: str, proxy: str = "") -> bool:
    """Cập nhật nhanh proxy cho profile."""
    try:
        resp = requests.get(
            f"{GPM_API_URL}/v2/update-proxy",
            params={"id": profile_id, "proxy": proxy},
            timeout=10
        )
        return resp.text.strip().lower() == "true"
    except Exception as e:
        log(f"  ❌ Lỗi khi cập nhật proxy: {e}")
        return False


def cap_nhat_note_gpm(profile_id: str, note: str = "") -> bool:
    """Cập nhật nhanh ghi chú cho profile."""
    try:
        resp = requests.get(
            f"{GPM_API_URL}/v2/update-note",
            params={"id": profile_id, "note": note},
            timeout=10
        )
        return resp.text.strip().lower() == "true"
    except Exception as e:
        log(f"  ❌ Lỗi khi cập nhật note: {e}")
        return False


def xoa_profile_gpm(profile_id: str, mode: int = 2) -> bool:
    """
    Xóa profile trên GPM-Login.
    mode=1: Chỉ xóa trên app; mode=2: Xóa cả folder dữ liệu profile.
    """
    try:
        resp = requests.get(
            f"{GPM_API_URL}/v2/delete",
            params={"profile_id": profile_id, "mode": mode},
            timeout=10
        )
        return "OK" in resp.text
    except Exception as e:
        log(f"  ❌ Lỗi khi xóa profile: {e}")
        return False


# ── Parse response ────────────────────────────────────────────────

def _trich_debug_addr(data: dict) -> str | None:
    """Trích remote debugging address từ GPM API response."""
    if not isinstance(data, dict):
        return None

    KEY_CANDIDATES = [
        "selenium_remote_debug_address",
        "remote_debugging_address",
        "debuggerAddress", "debugger_address",
        "ws_endpoint", "wsEndpoint",
        "debug_address", "debug_port",
        "remote_debug_address", "remote_debugging_port",
    ]

    search_targets = [data]
    if isinstance(data.get("data"), dict):
        search_targets.append(data["data"])

    for target in search_targets:
        for key in KEY_CANDIDATES:
            val = target.get(key)
            if val:
                val = str(val).strip()
                if val.isdigit():
                    return f"127.0.0.1:{val}"
                val = re.sub(r"^ws://", "", val)
                val = val.split("/")[0]
                if ":" in val:
                    return val

    raw = str(data)
    m = re.search(r"127\.0\.0\.1:(\d{4,5})", raw)
    if m:
        return f"127.0.0.1:{m.group(1)}"
    return None


# ── Kết nối Selenium ─────────────────────────────────────────────

def mo_profile_gpm(
    profile_id: str,
    gpmdriver_path: str = None,
    remote_debug_port: int = None,
    addination_args: str = None,
) -> webdriver.Chrome | None:
    """
    Nhờ GPM start profile (GPM lo proxy + fingerprint),
    rồi kết nối Selenium qua remote debugging port.
    Tự động nhận diện selenium_driver_location do API trả về.
    """
    params = {"profile_id": profile_id}
    if remote_debug_port:
        params["remote_debug_port"] = remote_debug_port
    if addination_args:
        params["addination_args"] = addination_args

    try:
        resp = requests.get(
            f"{GPM_API_URL}/v2/start",
            params=params,
            timeout=60
        )
        data = resp.json()
    except Exception as e:
        log(f"  ❌ GPM API start lỗi: {e}")
        return None

    log(f"  📥 GPM response keys: {list(data.keys()) if isinstance(data, dict) else data}")

    remote_addr = _trich_debug_addr(data)
    if not remote_addr:
        log("  ❌ Không tìm thấy debug address. Full response:")
        log(f"     {data}")
        return None

    driver_path = gpmdriver_path
    if isinstance(data, dict):
        gpm_driver = (data.get("selenium_driver_location")
                      or (data.get("data") or {}).get("selenium_driver_location"))
        if gpm_driver and os.path.exists(gpm_driver):
            driver_path = gpm_driver

    if not driver_path:
        driver_path = tim_gpmdriver()

    if not driver_path:
        log("  ❌ Không tìm thấy gpmdriver/chromedriver hợp lệ!")
        return None

    log(f"  🔗 Debug: {remote_addr}  |  Driver: {os.path.basename(driver_path)}")

    for attempt in range(10):
        time.sleep(3)
        try:
            r = requests.get(f"http://{remote_addr}/json/version", timeout=3)
            if r.status_code == 200:
                log(f"  ✅ Browser sẵn sàng (sau {(attempt+1)*3}s)")
                break
        except Exception:
            pass
        if attempt == 9:
            log("  ❌ Browser không phản hồi sau 30s")
            return None

    options = ChromeOptions()
    options.debugger_address = remote_addr
    service = ChromeService(executable_path=driver_path, log_output=os.devnull)

    try:
        driver = webdriver.Chrome(service=service, options=options)
        configure_driver_transport(driver)
        driver.set_page_load_timeout(60)
        driver.set_script_timeout(30)
        try:
            driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"}
            )
        except Exception:
            pass
        return driver
    except Exception as e:
        log(f"  ❌ Không kết nối Selenium: {e}")
        return None


# ── Kiểm tra proxy ────────────────────────────────────────────────

def kiem_tra_proxy_nhanh(driver, timeout=12) -> bool:
    """Load Google để kiểm tra proxy còn sống không."""
    if not safe_get(driver, "https://www.google.com", timeout=timeout):
        return False
    url = selenium_call(
        lambda: driver.current_url,
        driver=driver,
        timeout=8,
        default="",
    )
    title = selenium_call(
        lambda: driver.execute_script("return document.title"),
        driver=driver,
        timeout=8,
        default="",
    )
    return "google" in (url or "").lower() or bool(title)
