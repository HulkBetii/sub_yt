# -*- coding: utf-8 -*-
"""Chrome DevTools Protocol — ad blocking, anti-detect, sinh trắc học di chuột Fitts & native events."""
import math
import random
import time
from .logger import log
from .selenium_utils import selenium_call

SCROLL_COMMAND_TIMEOUT = 8

# ── Ad network blocking ───────────────────────────────────────────
_CDP_BLOCKED = [
    "*doubleclick.net*", "*googlesyndication.com*", "*googleadservices.com*",
    "*adservice.google.*", "*pagead2.googlesyndication*",
    "*securepubads.g.doubleclick*", "*pubads.g.doubleclick*",
    "*cm.g.doubleclick*", "*ad.doubleclick*",
    "*taboola.com*", "*outbrain.com*", "*mgid.com*", "*criteo.com*",
    "*adnxs.com*", "*amazon-adsystem.com*", "*adsrvr.org*",
    "*rubiconproject.com*", "*openx.net*", "*pubmatic.com*",
]

# ── JavaScript injected on every new page ────────────────────────
_YT_AD_SKIP_SCRIPT = """
(function() {
    'use strict';
    var _lastSkip = 0;

    var SKIP_TEXTS = [
        'skip', 'skip ad', 'skip ads', 'b\\u1ecf qua', '\\u30b9\\u30ad\\u30c3\\u30d7',
        '\\uac74\\ub108\\ub6f0\\uae30', '\\u8df3\\u8fc7', '\\u8df3\\u904e',
        '\\xfcberspringen', 'passer', 'saltar', 'sla over',
    ];

    function containsSkipText(el) {
        var t = (el.textContent || el.innerText || el.getAttribute('aria-label') || '').toLowerCase().trim();
        for (var i = 0; i < SKIP_TEXTS.length; i++) {
            if (t.indexOf(SKIP_TEXTS[i]) >= 0) return true;
        }
        return false;
    }

    function tryClick(el) {
        if (!el) return false;
        try { el.click(); return true; } catch(e) { return false; }
    }

    function skipAd() {
        var now = Date.now();
        if (now - _lastSkip < 600) return;

        var SELS = [
            '.ytp-skip-ad-button', '.ytp-ad-skip-button',
            'button.ytp-ad-skip-button-modern', '.ytp-ad-skip-button-slot button',
            '.ytp-skip-ad-button-modern', '[class*="skip-ad"]',
            '[class*="skipAd"]', '[class*="SkipAd"]', 'button[id*="skip"]',
        ];
        for (var i = 0; i < SELS.length; i++) {
            var el = document.querySelector(SELS[i]);
            if (el && tryClick(el)) { _lastSkip = now; return; }
        }

        var allEls = document.querySelectorAll('button[aria-label], .ytp-button[aria-label]');
        for (var j = 0; j < allEls.length; j++) {
            if (containsSkipText(allEls[j]) && tryClick(allEls[j])) {
                _lastSkip = now; return;
            }
        }

        var playerBtns = document.querySelectorAll('.html5-video-player button, #movie_player button');
        for (var k = 0; k < playerBtns.length; k++) {
            var btn = playerBtns[k];
            if (containsSkipText(btn)) {
                var rect = btn.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0 && tryClick(btn)) {
                    _lastSkip = now; return;
                }
            }
        }

        var banner = document.querySelector(
            '.ytp-ad-overlay-close-button, .ytp-ad-text-overlay .ytp-ad-overlay-close-button'
        );
        if (banner && tryClick(banner)) { _lastSkip = now; }
    }

    setInterval(skipAd, 600);
})();
"""

_ANTI_DETECT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
window.chrome = window.chrome || {runtime: {}};
"""


# ── CDP setup ─────────────────────────────────────────────────────

def cdp_setup(driver):
    """Block ads + inject anti-detect + YT ad-skip script."""
    _cursor[0], _cursor[1] = 400, 300
    try:
        driver.execute_cdp_cmd("Network.enable", {})
        driver.execute_cdp_cmd("Network.setBlockedURLs", {"urls": _CDP_BLOCKED})
    except Exception:
        pass
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": _ANTI_DETECT_SCRIPT + _YT_AD_SKIP_SCRIPT}
        )
    except Exception:
        pass


# ── CDP native events ─────────────────────────────────────────────

def cdp_scroll(driver, delta_y: int):
    """Scroll smoothly via WheelEvent."""
    selenium_call(
        lambda: driver.execute_script(
            """
            window.dispatchEvent(new WheelEvent('wheel', {deltaY: arguments[0]}));
            window.scrollBy({top: arguments[0], left: 0, behavior: 'smooth'});
            """,
            delta_y,
        ),
        driver=driver,
        timeout=SCROLL_COMMAND_TIMEOUT,
        default=None,
    )


# ── Bézier mouse movement with Fitts's Law Dynamics ───────────────

_cursor = [400, 300]   # Module-level cursor position tracking


def _bezier_pts(p0, cp1, cp2, p3, n_steps: int = 15) -> list:
    """Sinh n_steps điểm trên đường cong Bézier bậc 3 có jitter sinh học."""
    if n_steps <= 1:
        return [p0, p3]
    pts = []
    for i in range(n_steps):
        t = i / (n_steps - 1)
        u = 1 - t
        x = u**3 * p0[0] + 3 * u**2 * t * cp1[0] + 3 * u * t**2 * cp2[0] + t**3 * p3[0]
        y = u**3 * p0[1] + 3 * u**2 * t * cp1[1] + 3 * u * t**2 * cp2[1] + t**3 * p3[1]

        # Rung tay sinh học (micro-jitter) ở khoảng giữa
        if 0.15 < t < 0.85:
            jitter_x = random.gauss(0, 0.8)
            jitter_y = random.gauss(0, 0.8)
            x += jitter_x
            y += jitter_y

        pts.append((int(round(x)), int(round(y))))
    return pts


def bezier_mouse_move(driver, tx: int, ty: int, allow_overshoot: bool = True):
    """
    Di chuột theo mô hình Định luật Fitts (Fitts's Law Velocity Profile):
    - Tăng tốc nhanh 40% đoạn đầu, đạt đỉnh vận tốc.
    - Giảm tốc từ từ và có vi điều chỉnh (micro-corrections) ở đích.
    - Có xác suất vượt điểm đích nhẹ (overshoot 6-15px) rồi giật lại.
    """
    x0, y0 = _cursor
    dist = math.hypot(tx - x0, ty - y0)
    if dist < 4:
        return

    # Xác định số bước theo khoảng cách (12 - 35 bước)
    n_steps = max(12, min(35, int(dist / 22)))

    # Có overshoot không (35% khi di chuyển khoảng cách > 120px)
    do_overshoot = allow_overshoot and dist > 120 and random.random() < 0.35
    if do_overshoot:
        angle = math.atan2(ty - y0, tx - x0)
        overshoot_len = random.uniform(8, 18)
        ox = tx + int(math.cos(angle) * overshoot_len) + random.randint(-4, 4)
        oy = ty + int(math.sin(angle) * overshoot_len) + random.randint(-4, 4)
        target_pt = (ox, oy)
    else:
        target_pt = (tx, ty)

    dx, dy = target_pt[0] - x0, target_pt[1] - y0
    cp1 = (
        x0 + dx * random.uniform(0.2, 0.4) + random.randint(-35, 35),
        y0 + dy * random.uniform(0.1, 0.3) + random.randint(-30, 30),
    )
    cp2 = (
        x0 + dx * random.uniform(0.6, 0.8) + random.randint(-35, 35),
        y0 + dy * random.uniform(0.7, 0.9) + random.randint(-30, 30),
    )

    pts = _bezier_pts((x0, y0), cp1, cp2, target_pt, n_steps)

    # Nếu có overshoot, thêm các điểm sửa sai quay về đúng đích
    if do_overshoot:
        correction_steps = random.randint(3, 6)
        corr_cp1 = (target_pt[0] + (tx - target_pt[0]) * 0.5, target_pt[1] + (ty - target_pt[1]) * 0.5)
        corr_pts = _bezier_pts(target_pt, corr_cp1, corr_cp1, (tx, ty), correction_steps)
        pts.extend(corr_pts[1:])

    # Thực hiện di chuyển theo profile tốc độ Fitts
    total_pts = len(pts)
    for i, (px, py) in enumerate(pts):
        try:
            driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
                "type": "mouseMoved", "x": max(0, px), "y": max(0, py),
                "modifiers": 0, "buttons": 0, "button": "none",
            })
            # Tốc độ: nhanh nhất ở 30-50% đoạn đường, chậm lại ở đầu và cuối
            t = (i + 1) / total_pts
            if t < 0.4:
                base_delay = 0.008 + 0.012 * (1.0 - t / 0.4)
            else:
                base_delay = 0.008 + 0.020 * ((t - 0.4) / 0.6)**1.5

            time.sleep(max(0.003, random.gauss(base_delay, 0.003)))
        except Exception:
            break

    _cursor[0], _cursor[1] = tx, ty


# Alias
cdp_move_mouse = bezier_mouse_move


def cdp_click(driver, element):
    """Click element: Di chuột Fitts Bézier -> mousePressed -> mouseReleased."""
    try:
        rect = driver.execute_script("""
            var r = arguments[0].getBoundingClientRect();
            return {x: r.left + r.width/2, y: r.top + r.height/2};
        """, element)
        x = int(rect["x"]) + random.randint(-3, 3)
        y = int(rect["y"]) + random.randint(-3, 3)

        bezier_mouse_move(driver, x, y)
        time.sleep(random.uniform(0.08, 0.22))

        for evt in ("mousePressed", "mouseReleased"):
            driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
                "type": evt, "x": x, "y": y, "modifiers": 0,
                "buttons": 1 if evt == "mousePressed" else 0,
                "button": "left", "clickCount": 1,
            })
            time.sleep(random.uniform(0.05, 0.12))
    except Exception:
        driver.execute_script("arguments[0].click();", element)


def cdp_drag_mouse(driver, start_x: int, start_y: int, end_x: int, end_y: int):
    """Kéo thả chuột (dùng để pan bản đồ Google Maps hoặc kéo thanh trượt)."""
    try:
        bezier_mouse_move(driver, start_x, start_y)
        time.sleep(random.uniform(0.1, 0.25))

        driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": start_x, "y": start_y,
            "modifiers": 0, "buttons": 1, "button": "left", "clickCount": 1,
        })
        time.sleep(0.1)

        dx, dy = end_x - start_x, end_y - start_y
        cp1 = (start_x + dx * 0.3 + random.randint(-15, 15), start_y + dy * 0.3 + random.randint(-15, 15))
        cp2 = (start_x + dx * 0.7 + random.randint(-15, 15), start_y + dy * 0.7 + random.randint(-15, 15))
        pts = _bezier_pts((start_x, start_y), cp1, cp2, (end_x, end_y), random.randint(10, 18))

        for px, py in pts:
            driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
                "type": "mouseMoved", "x": px, "y": py,
                "modifiers": 0, "buttons": 1, "button": "left",
            })
            time.sleep(random.uniform(0.015, 0.035))

        driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": end_x, "y": end_y,
            "modifiers": 0, "buttons": 0, "button": "left", "clickCount": 1,
        })
        time.sleep(random.uniform(0.1, 0.2))
        _cursor[0], _cursor[1] = end_x, end_y
    except Exception:
        pass


def idle_drift(driver, duration_s: float):
    """Nhúc nhích chuột nhẹ khi người dùng đang đọc bài hoặc xem video."""
    t_end = time.time() + duration_s
    while time.time() < t_end:
        rem = t_end - time.time()
        wait = min(rem, random.uniform(3.0, 9.0))
        time.sleep(wait)
        if random.random() < 0.55:
            cx, cy = _cursor
            nx = max(50, min(1200, cx + random.randint(-40, 40)))
            ny = max(50, min(700, cy + random.randint(-30, 30)))
            bezier_mouse_move(driver, nx, ny, allow_overshoot=False)
