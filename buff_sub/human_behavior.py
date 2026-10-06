# -*- coding: utf-8 -*-
"""Mô phỏng hành vi người thật: cuộn quán tính, hover Fitts, gõ phím QWERTY sinh học, Autocomplete & Session Archetypes."""
import time
import random
from dataclasses import dataclass
from enum import Enum
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from .logger import log
from .selenium_utils import is_driver_healthy, selenium_call
from .cdp import cdp_scroll, bezier_mouse_move


# ════════════════════════════════════════════════════════════════
#  SESSION ARCHETYPES — 3 dạng phiên người dùng
# ════════════════════════════════════════════════════════════════

class SessionArchetype(Enum):
    QUICK_CHECK   = "quick_check"    # 30%: Lướt nhanh 2-5p (1 video hoặc 1 search)
    CASUAL_BROWSE = "casual_browse"  # 50%: Bình thường 8-15p (2-3 video + 1-2 web)
    DEEP_DIVE     = "deep_dive"      # 20%: Đào sâu 25-45p (nghe podcast, đọc chuỗi bài)


def draw_session_archetype() -> SessionArchetype:
    """Rút ngẫu nhiên dạng phiên duyệt web cho profile."""
    roll = random.random()
    if roll < 0.30:
        return SessionArchetype.QUICK_CHECK
    elif roll < 0.80:
        return SessionArchetype.CASUAL_BROWSE
    else:
        return SessionArchetype.DEEP_DIVE


# ════════════════════════════════════════════════════════════════
#  SESSION MOOD — personality được chọn 1 lần/profile
# ════════════════════════════════════════════════════════════════

@dataclass
class SessionMood:
    name: str
    archetype: SessionArchetype
    # ── In-video interaction probs ────────────────────────────────
    pause_prob: float        # Xác suất pause/resume mỗi chunk
    seek_fwd_prob: float     # Xác suất tua tiến
    seek_bwd_prob: float     # Xác suất tua lùi
    comment_prob: float      # Xác suất cuộn xuống đọc comment
    like_prob: float         # Xác suất hover nút Like
    like_click_prob: float   # Xác suất thực sự bấm Like
    vol_prob: float          # Xác suất hover thanh âm lượng
    related_prob: float      # Xác suất hover video liên quan
    chunk_skip_prob: float   # Xác suất xem lặng lẽ (không interact chunk này)
    early_exit_prob: float   # Xác suất thoát video trước khi hết
    early_exit_ratio: tuple  # (min, max) ratio thời lượng trước khi thoát
    # ── Session-level behavior probs ────────────────────────────
    notif_open_prob: float   # Xác suất mở notification panel thật
    channel_visit_prob: float # Xác suất visit channel page sau video
    quality_change_prob: float # Xác suất đổi chất lượng video
    subtitle_prob: float     # Xác suất bật/tắt CC/Subtitles
    speed_change_prob: float # Xác suất đổi tốc độ phát (0.75×/1.25×/1.5×)
    fullscreen_prob: float   # Xác suất fullscreen rồi thoát
    theater_prob: float      # Xác suất theater mode (phím t)
    watch_later_prob: float  # Xác suất lưu vào Watch Later
    desc_expand_prob: float  # Xác suất mở rộng description
    rabbit_hole_prob: float  # Xác suất xem depth-2 (related của related)


def draw_session_mood() -> SessionMood:
    """Chọn ngẫu nhiên personality & archetype cho session này."""
    arch = draw_session_archetype()
    roll = random.random()

    if roll < 0.28:
        # Passive: lười tương tác, ít dùng tính năng
        return SessionMood(
            name="passive", archetype=arch,
            pause_prob=0.05, seek_fwd_prob=0.06, seek_bwd_prob=0.03,
            comment_prob=0.04, like_prob=0.03, like_click_prob=0.08,
            vol_prob=0.02, related_prob=0.03, chunk_skip_prob=0.55,
            early_exit_prob=0.22, early_exit_ratio=(0.20, 0.55),
            notif_open_prob=0.05, channel_visit_prob=0.05,
            quality_change_prob=0.04, subtitle_prob=0.03,
            speed_change_prob=0.02, fullscreen_prob=0.05,
            theater_prob=0.04, watch_later_prob=0.02,
            desc_expand_prob=0.06, rabbit_hole_prob=0.05
        )
    elif roll < 0.68:
        # Normal: tương tác vừa phải
        return SessionMood(
            name="normal", archetype=arch,
            pause_prob=0.18, seek_fwd_prob=0.12, seek_bwd_prob=0.08,
            comment_prob=0.09, like_prob=0.07, like_click_prob=0.28,
            vol_prob=0.05, related_prob=0.05, chunk_skip_prob=0.28,
            early_exit_prob=0.10, early_exit_ratio=(0.30, 0.65),
            notif_open_prob=0.15, channel_visit_prob=0.20,
            quality_change_prob=0.12, subtitle_prob=0.08,
            speed_change_prob=0.10, fullscreen_prob=0.15,
            theater_prob=0.12, watch_later_prob=0.08,
            desc_expand_prob=0.18, rabbit_hole_prob=0.15
        )
    else:
        # Engaged: xem kỹ, tương tác nhiều, dùng nhiều tính năng
        return SessionMood(
            name="engaged", archetype=arch,
            pause_prob=0.25, seek_fwd_prob=0.16, seek_bwd_prob=0.10,
            comment_prob=0.14, like_prob=0.12, like_click_prob=0.45,
            vol_prob=0.07, related_prob=0.08, chunk_skip_prob=0.08,
            early_exit_prob=0.04, early_exit_ratio=(0.50, 0.80),
            notif_open_prob=0.30, channel_visit_prob=0.40,
            quality_change_prob=0.20, subtitle_prob=0.18,
            speed_change_prob=0.22, fullscreen_prob=0.28,
            theater_prob=0.20, watch_later_prob=0.18,
            desc_expand_prob=0.35, rabbit_hole_prob=0.28
        )


# ── Helpers ───────────────────────────────────────────────────────

def delay(min_s=1.0, max_s=3.0):
    time.sleep(random.uniform(min_s, max_s))


def nghi_ngau_nhien(ty_le=0.25):
    """Ngẫu nhiên dừng lại như đang suy nghĩ."""
    if random.random() < ty_le:
        time.sleep(random.uniform(2.0, 6.0))


def kiem_tra_ket_noi(driver) -> bool:
    """Kiểm tra browser còn sống bằng transport timeout thật."""
    if not is_driver_healthy(driver):
        return False
    try:
        url = selenium_call(
            lambda: driver.current_url,
            driver=driver,
            timeout=10,
            default=None,
        )
        return url is not None
    except Exception:
        return False


# ── Cuộn quán tính & Backtracking (Attention Tracking) ───────────

def cuon_tu_nhien(driver, huong="xuong", so_lan=None, cho_phep_backtrack=True):
    """
    Cuộn tự nhiên qua CDP WheelEvent:
    - Quán tính phi tuyến tính (Inertial easing).
    - Dừng nghỉ đọc nội dung (Micro-reading pauses).
    - Có xác suất 25% cuộn ngược lại (Backtracking 100-250px) để xem lại tiêu đề/ảnh.
    """
    so_lan = so_lan or random.randint(3, 8)
    for step in range(so_lan):
        if not kiem_tra_ket_noi(driver):
            break

        if huong == "xuong":
            px = random.randint(150, 450)
        else:
            px = -random.randint(150, 350)

        try:
            # Chia thành 3-6 bước nhỏ với gia tốc giảm dần
            buoc = random.randint(3, 6)
            for b in range(buoc):
                fraction = (buoc - b) / buoc
                delta = int((px / buoc) * (0.6 + 0.8 * fraction))
                cdp_scroll(driver, delta)
                time.sleep(random.uniform(0.02, 0.08))
        except Exception:
            break

        # Khoảng dừng đọc bài tự nhiên
        time.sleep(random.uniform(0.8, 2.8))

        # 25% xác suất Backtrack: cuộn ngược nhẹ để xem lại nội dung vừa lướt qua
        if cho_phep_backtrack and huong == "xuong" and random.random() < 0.25:
            backtrack_px = -random.randint(100, 220)
            try:
                cdp_scroll(driver, backtrack_px)
                time.sleep(random.uniform(1.5, 4.0))  # Dừng đọc nội dung
            except Exception:
                pass


def hover_element(driver, element):
    """Di chuột lên phần tử theo đường cong Bézier & Fitts Law."""
    try:
        rect = selenium_call(
            lambda: driver.execute_script("""
                var r = arguments[0].getBoundingClientRect();
                return {x: r.left + r.width/2, y: r.top + r.height/2, ok: r.width > 0};
            """, element),
            driver=driver,
            timeout=8,
            default=None,
        )
        if not rect or not rect.get("ok"):
            return
        bezier_mouse_move(driver, int(rect["x"]), int(rect["y"]))
        time.sleep(random.uniform(0.15, 0.45))
    except Exception:
        return


def hover_vi_tri_ngau_nhien(driver):
    """Di chuột đến vị trí ngẫu nhiên trên màn hình."""
    try:
        viewport = selenium_call(
            lambda: driver.execute_script(
                "return {w: window.innerWidth || 1280, h: window.innerHeight || 720};"
            ),
            driver=driver,
            timeout=5,
            default=None,
        )
        if not viewport:
            return
        w = int(viewport.get("w") or 1280)
        h = int(viewport.get("h") or 720)
        x = random.randint(100, max(101, w - 100))
        y = random.randint(100, max(101, h - 100))
        bezier_mouse_move(driver, x, y)
        time.sleep(random.uniform(0.2, 0.6))
    except Exception:
        pass


# ── Gõ phím QWERTY Sinh Học & Autocomplete ─────────────────────────

_QWERTY_ADJACENT = {
    'q': 'wa', 'w': 'qes', 'e': 'wrd', 'r': 'etf', 't': 'ryg', 'y': 'tuh',
    'u': 'yij', 'i': 'uok', 'o': 'ipl', 'p': 'ol', 'a': 'qwsz', 's': 'awedxz',
    'd': 'serfcx', 'f': 'drtgvc', 'g': 'ftyhbv', 'h': 'gyujnb', 'j': 'huikmn',
    'k': 'jiolm', 'l': 'kop', 'z': 'asx', 'x': 'zsdc', 'c': 'xdfv', 'v': 'cfgb',
    'b': 'vghn', 'n': 'bhjm', 'm': 'njk',
}


def go_co_loi_chinh_ta(element, text: str):
    """
    Gõ phím sinh học:
    - 6% gõ nhầm phím QWERTY lân cận rồi bấm Backspace sửa.
    - Khoảng dừng giữa các từ (phím Space) dài hơn khoảng dừng giữa các ký tự.
    """
    for i, ch in enumerate(text):
        # 6% xác suất gõ nhầm phím lân cận
        if ch.lower() in _QWERTY_ADJACENT and random.random() < 0.06 and i < len(text) - 1:
            wrong_char = random.choice(_QWERTY_ADJACENT[ch.lower()])
            element.send_keys(wrong_char)
            time.sleep(random.uniform(0.12, 0.28))
            element.send_keys(Keys.BACK_SPACE)
            time.sleep(random.uniform(0.08, 0.20))

        element.send_keys(ch)

        # Khoảng dừng nhận thức giữa các từ (dấu cách)
        if ch == ' ':
            time.sleep(random.uniform(0.14, 0.40))
        else:
            time.sleep(random.uniform(0.03, 0.16))

        # Thỉnh thoảng ngập ngừng suy nghĩ (4% xác suất)
        if random.random() < 0.04:
            time.sleep(random.uniform(0.3, 0.9))


def go_voi_autocomplete(driver, element, text: str, min_chars: int = 5) -> bool:
    """
    Gõ 5-8 ký tự đầu, ngắm gợi ý xổ xuống (Autocomplete Dropdown),
    dùng phím ArrowDown chọn rồi bấm Enter (hành vi 100% người thật).
    """
    try:
        # Gõ một phần từ khóa
        cut_len = min(len(text), max(min_chars, int(len(text) * random.uniform(0.4, 0.7))))
        prefix = text[:cut_len]
        go_co_loi_chinh_ta(element, prefix)

        # Dừng ngắm kết quả dropdown
        time.sleep(random.uniform(0.8, 1.8))

        # Bấm ArrowDown 1-3 lần để chọn gợi ý
        arrow_times = random.randint(1, 3)
        for _ in range(arrow_times):
            element.send_keys(Keys.ARROW_DOWN)
            time.sleep(random.uniform(0.2, 0.5))

        delay(0.4, 0.9)
        element.send_keys(Keys.RETURN)
        return True
    except Exception:
        element.send_keys(Keys.RETURN)
        return False


def chon_van_ban_ngau_nhien(driver):
    """Bôi đen đoạn văn ngẫu nhiên như đang đọc kỹ."""
    try:
        paras = driver.find_elements(By.CSS_SELECTOR, "p, h2, h3, li, span")
        valids = [p for p in paras if p.text.strip() and len(p.text) > 20]
        if not valids:
            return
        para = random.choice(valids[:15])
        selenium_call(
            lambda: driver.execute_script("arguments[0].scrollIntoView({block:'center'});", para),
            driver=driver,
            timeout=8,
            default=None,
        )
        time.sleep(random.uniform(0.5, 1.0))
        selenium_call(
            lambda: driver.execute_script(
                """
                const el = arguments[0];
                const selection = window.getSelection();
                const range = document.createRange();
                range.selectNodeContents(el);
                selection.removeAllRanges();
                selection.addRange(range);
                """,
                para,
            ),
            driver=driver,
            timeout=8,
            default=None,
        )
        time.sleep(random.uniform(0.4, 1.0))
        selenium_call(
            lambda: driver.execute_script("window.getSelection().removeAllRanges();"),
            driver=driver,
            timeout=5,
            default=None,
        )
    except Exception:
        pass


def phim_tat_ngau_nhien(driver):
    """Thỉnh thoảng dùng Ctrl+F hoặc cuộn lên đầu trang."""
    hd = random.random()
    try:
        body = driver.find_element(By.TAG_NAME, "body")
        if hd < 0.15:
            body.send_keys(Keys.CONTROL, "f")
            time.sleep(random.uniform(1.0, 2.5))
            body.send_keys(Keys.ESCAPE)
        elif hd < 0.25:
            driver.execute_script("window.scrollTo({top: 0, behavior: 'smooth'});")
            time.sleep(random.uniform(0.5, 1.5))
    except Exception:
        pass
