# -*- coding: utf-8 -*-
"""Bảo vệ tab — phát hiện và đóng tab quảng cáo bật lên."""
import time

from .config import DOMAINS_QUANG_CAO
from .logger import log
from .selenium_utils import (
    focus_content_tab,
    selenium_call,
    safe_window_handles,
)
from .human_behavior import kiem_tra_ket_noi


def la_url_quang_cao(url: str) -> bool:
    """Kiểm tra URL có phải quảng cáo không."""
    if not url or url.strip() == "":
        return True
    if url.startswith("data:"):
        return True
    if url.startswith("chrome-extension://"):
        return True
    url_lower = url.lower()
    if url_lower in ("about:blank", "about:newtab", "about:home"):
        return True
    for domain in DOMAINS_QUANG_CAO:
        if domain in url_lower:
            return True
    return False


def _dong_tab_phu(driver, handles_goc):
    """Đóng tất cả tab phụ và quay về tab gốc."""
    try:
        for h in list(driver.window_handles):
            if h not in handles_goc:
                driver.switch_to.window(h)
                driver.close()
        driver.switch_to.window(list(handles_goc)[0])
    except Exception:
        pass


def don_dep_tab_la(driver, handles_cho_phep: set = None, tab_quay_ve: str = None) -> int:
    """Đóng tab nằm ngoài handles_cho_phep. Trả về số tab đã đóng."""
    so_dong = 0
    try:
        handles_hien_tai = safe_window_handles(driver)
        if not handles_hien_tai:
            return 0
        
        if handles_cho_phep is None:
            # Nếu không chỉ định handles_cho_phep, đóng các tab có URL quảng cáo/about:blank
            for h in list(handles_hien_tai):
                try:
                    if len(handles_hien_tai) <= 1:
                        break
                    selenium_call(
                        lambda h=h: driver.switch_to.window(h),
                        driver=driver,
                        timeout=5,
                    )
                    url = selenium_call(
                        lambda: driver.current_url,
                        driver=driver,
                        timeout=5,
                        default="",
                    )
                    if la_url_quang_cao(url):
                        log(f"    🚫 Đóng tab lạ [{(url or '')[:55]}]")
                        selenium_call(
                            lambda: driver.close(),
                            driver=driver,
                            timeout=5,
                        )
                        so_dong += 1
                        handles_hien_tai = safe_window_handles(driver)
                except Exception:
                    pass
            con_lai = safe_window_handles(driver)
            if con_lai:
                focus_content_tab(
                    driver,
                    preferred_handle=tab_quay_ve,
                    create_if_missing=False,
                )
            return so_dong

        tab_la = handles_hien_tai - handles_cho_phep
        for h in list(tab_la):
            try:
                ok = selenium_call(
                    lambda h=h: driver.switch_to.window(h),
                    driver=driver,
                    timeout=5,
                )
                if ok is None:
                    continue
                url = selenium_call(
                    lambda: driver.current_url,
                    driver=driver,
                    timeout=5,
                    default="",
                )
                log(f"    🚫 Đóng tab lạ [{(url or '')[:55]}]")
                selenium_call(
                    lambda: driver.close(),
                    driver=driver,
                    timeout=5,
                )
                so_dong += 1
            except Exception:
                pass
        con_lai = safe_window_handles(driver)
        if not con_lai:
            return so_dong
        preferred = tab_quay_ve if tab_quay_ve in con_lai else None
        focus_content_tab(
            driver,
            preferred_handle=preferred,
            create_if_missing=False,
        )
    except Exception:
        pass
    if so_dong:
        log(f"    ✅ Đã đóng {so_dong} tab quảng cáo/lạ")
    return so_dong


def click_an_toan(driver, element, handles_cho_phep: set,
                  cho_tab_moi: bool = False, timeout_tab: float = 1.5):
    """
    Click element, tự động đóng tab quảng cáo bật ra.
    cho_tab_moi=True → giữ lại tab hợp lệ và trả về handle.
    """
    tab_hien_tai = driver.current_window_handle
    handles_truoc = safe_window_handles(driver)
    try:
        driver.execute_script("arguments[0].click();", element)
    except Exception:
        return None

    time.sleep(timeout_tab)
    handles_sau = safe_window_handles(driver)
    tab_moi_xuat_hien = handles_sau - handles_truoc

    if not tab_moi_xuat_hien:
        return None

    if not cho_tab_moi:
        don_dep_tab_la(driver, handles_cho_phep, tab_hien_tai)
        return None

    tab_hop_le = None
    for h in list(tab_moi_xuat_hien):
        try:
            driver.switch_to.window(h)
            try:
                WebDriverWait(driver, 2.0).until(
                    lambda d: d.current_url not in ("about:blank", "")
                )
            except Exception:
                pass
            url = driver.current_url
            if la_url_quang_cao(url):
                log(f"    🚫 Đóng tab quảng cáo: [{url[:55]}]")
                driver.close()
            else:
                tab_hop_le = h
        except Exception:
            try:
                driver.close()
            except Exception:
                pass

    don_dep_tab_la(
        driver,
        handles_cho_phep | ({tab_hop_le} if tab_hop_le else set()),
        tab_hop_le or tab_hien_tai
    )
    return tab_hop_le


def watchdog_tabs(driver, handles_cho_phep: set, tab_hien_tai: str) -> bool:
    """
    Phát hiện và đóng tab lạ trong vòng lặp dài.
    Trả về True nếu browser OK, False nếu crash.
    """
    if not kiem_tra_ket_noi(driver):
        return False

    handles_hien_tai = selenium_call(
        lambda: set(driver.window_handles),
        driver=driver,
        timeout=10,
        default=None,
    )
    if handles_hien_tai is None:
        return False

    if not focus_content_tab(
        driver,
        preferred_handle=tab_hien_tai,
        create_if_missing=False,
    ):
        return False

    tab_la = handles_hien_tai - handles_cho_phep
    if tab_la:
        don_dep_tab_la(driver, handles_cho_phep, tab_hien_tai)

    return kiem_tra_ket_noi(driver)
