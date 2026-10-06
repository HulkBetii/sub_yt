# -*- coding: utf-8 -*-
"""
sub_engine.py — Organic YouTube Subscription Execution Engine
Implements natural mouse movement, Shadow DOM traversal, human retention viewing,
like probability, subscribe verification, and clean lifecycle management.
"""
import time
import random
from typing import Optional, Dict, Any, List, Tuple
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.webdriver import WebDriver

from .logger import log
from .config import (
    WARMUP_VIDEO_WATCH_MIN,
    WARMUP_VIDEO_WATCH_MAX,
    TARGET_VIDEO_WATCH_MIN,
    TARGET_VIDEO_WATCH_MAX,
    LIKE_PROBABILITY,
    COOLDOWN_POST_SUB_MIN,
    COOLDOWN_POST_SUB_MAX,
    COOLDOWN_DAYS_AFTER_SUB,
)
from .gpm_bridge import open_profile_session, close_profile_session
from .account_pool import (
    acquire_account_lock,
    update_cooldown,
    get_account,
)
from .database import (
    get_order,
    log_sub_attempt,
)
from .cdp import bezier_mouse_move, cdp_click, cdp_scroll, idle_drift
from .human_behavior import (
    draw_session_mood,
    cuon_tu_nhien,
    hover_element,
    delay,
    nghi_ngau_nhien,
)
from .selenium_utils import safe_get, safe_quit, selenium_call
from .tab_guard import don_dep_tab_la
from .health_monitor import (
    analyze_driver_health,
    suspend_account,
    check_cluster_health_and_protect,
    FATAL_CONDITIONS,
)
from .youtube_scraper import get_channel_latest_videos


# ── Selectors & Constants ────────────────────────────────────────

SUBSCRIBE_SELECTORS = [
    "#subscribe-button button",
    "ytd-subscribe-button-renderer button",
    "ytd-subscribe-button-renderer yt-button-shape button",
    "#subscribe-button ytd-button-renderer button",
    "button[aria-label*='Subscribe' i]",
    "button[aria-label*='Đăng ký' i]",
]

ALREADY_SUBSCRIBED_KEYWORDS = [
    "subscribed", "đã đăng ký", "hủy đăng ký", "unsubscribe"
]

LIKE_SELECTORS = [
    "ytd-watch-metadata ytd-like-button-renderer button",
    "#top-level-buttons-computed ytd-like-button-renderer button",
    "like-button-view-model button",
    "#like-button button",
    "ytd-like-button-renderer button",
    "button[aria-label*='like this video' i]",
    "button[aria-label*='thích video này' i]",
    "button[aria-label*='like' i]",
]

ALREADY_LIKED_KEYWORDS = [
    "unlike", "đã thích", "bỏ thích", "remove like"
]

AD_SKIP_SELECTORS = [
    ".ytp-skip-ad-button",
    ".ytp-ad-skip-button",
    "button.ytp-ad-skip-button-modern",
    ".ytp-skip-ad-button-modern",
    ".ytp-ad-skip-button-slot button",
    "[class*='skip-ad'] button",
    "[class*='skipAd']",
    "[class*='SkipAd']",
    "button[id*='skip']",
]

AD_SKIP_TEXTS = [
    "skip", "bỏ qua", "スキップ", "건너뛰기", "saltar", "passer"
]

AD_BANNER_CLOSE_SELECTORS = [
    ".ytp-ad-overlay-close-button",
    ".ytp-ad-overlay-close",
    ".ytp-ad-text-overlay .ytp-ad-overlay-close-button",
]


# ── Human-like Cursor & Interaction ──────────────────────────────

def human_click_element(driver: WebDriver, element: Any) -> bool:
    """
    Simulate human-like cursor approach and click on a target element via Selenium CDP.
    Uses Bézier curve with Fitts's Law dynamics (acceleration, deceleration, micro-jitter).
    1. Smoothly scrolls element into view.
    2. Computes bounding box with randomized offset within element box.
    3. Moves cursor along Bézier curve (bezier_mouse_move).
    4. Dispatches native CDP click (cdp_click).
    Fallback: JavaScript direct click if coordinates cannot be resolved.
    """
    if element is None:
        return False

    # 1. Smoothly scroll element towards center
    try:
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
        time.sleep(random.uniform(0.3, 0.6))
    except Exception:
        pass

    # 2. Primary: Bézier trajectory approach + CDP native click
    try:
        rect = driver.execute_script("return arguments[0].getBoundingClientRect();", element)
        if rect and rect.get("width", 0) > 0 and rect.get("height", 0) > 0:
            rx = int(rect["left"] + random.uniform(rect["width"] * 0.25, rect["width"] * 0.75))
            ry = int(rect["top"] + random.uniform(rect["height"] * 0.25, rect["height"] * 0.75))
            bezier_mouse_move(driver, rx, ry)
            time.sleep(random.uniform(0.15, 0.35))
            cdp_click(driver, rx, ry)
            time.sleep(random.uniform(0.4, 0.8))
            return True
    except Exception:
        pass

    # 3. Emergency Fallback: JavaScript click
    try:
        driver.execute_script("arguments[0].click();", element)
        time.sleep(0.5)
        return True
    except Exception:
        return False


def skip_youtube_ads(driver: WebDriver) -> bool:
    """Detect and dismiss/skip YouTube video ads."""
    # 1. Skip button selectors
    for sel in AD_SKIP_SELECTORS:
        try:
            btns = driver.find_elements(By.CSS_SELECTOR, sel)
            for btn in btns:
                if btn.is_displayed():
                    time.sleep(random.uniform(0.3, 0.8))
                    driver.execute_script("arguments[0].click();", btn)
                    log("    ⏭ Skipped YouTube ad via selector", "INFO")
                    time.sleep(0.5)
                    return True
        except Exception:
            pass

    # 2. Text-based skip button search
    try:
        buttons = driver.find_elements(
            By.CSS_SELECTOR,
            ".html5-video-player button, #movie_player button, .ytp-chrome-bottom button"
        )
        for btn in buttons:
            txt = (btn.text or btn.get_attribute("aria-label") or "").lower().strip()
            if any(k in txt for k in AD_SKIP_TEXTS):
                time.sleep(random.uniform(0.3, 0.6))
                driver.execute_script("arguments[0].click();", btn)
                log("    ⏭ Skipped YouTube ad via text match", "INFO")
                return True
    except Exception:
        pass

    # 3. Close banner overlay
    for sel in AD_BANNER_CLOSE_SELECTORS:
        try:
            btn = driver.find_element(By.CSS_SELECTOR, sel)
            if btn.is_displayed():
                driver.execute_script("arguments[0].click();", btn)
                return True
        except Exception:
            pass

    return False


def find_subscribe_button(driver: WebDriver) -> Tuple[Optional[Any], bool]:
    """
    Locate the Subscribe button on YouTube page.
    Traverses standard DOM and Polymer Shadow DOM.
    Returns: (element, is_already_subscribed)
    """
    # 1. Standard DOM search
    for sel in SUBSCRIBE_SELECTORS:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in elements:
                if el.is_displayed():
                    text = (el.text or el.get_attribute("aria-label") or "").lower()
                    already_subbed = any(w in text for w in ALREADY_SUBSCRIBED_KEYWORDS)
                    return el, already_subbed
        except Exception:
            pass

    # 2. Piercing Shadow DOM fallback via JavaScript
    try:
        el = driver.execute_script("""
            let renderer = document.querySelector('ytd-subscribe-button-renderer');
            if (!renderer) return null;
            if (renderer.shadowRoot) {
                let btn = renderer.shadowRoot.querySelector('button, [role="button"]');
                if (btn) return btn;
            }
            return renderer.querySelector('button, [role="button"]');
        """)
        if el and el.is_displayed():
            text = (el.text or el.get_attribute("aria-label") or "").lower()
            already_subbed = any(w in text for w in ALREADY_SUBSCRIBED_KEYWORDS)
            return el, already_subbed
    except Exception:
        pass

    return None, False


def find_like_button(driver: WebDriver) -> Tuple[Optional[Any], bool]:
    """
    Locate the Like button on YouTube video watch page.
    Returns: (element, is_already_liked)
    """
    # 1. Standard DOM search
    for sel in LIKE_SELECTORS:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in elements:
                if el.is_displayed():
                    label = (el.get_attribute("aria-label") or el.text or "").lower()
                    pressed = el.get_attribute("aria-pressed") == "true"
                    already_liked = pressed or any(w in label for w in ALREADY_LIKED_KEYWORDS)
                    return el, already_liked
        except Exception:
            pass

    # 2. Piercing Shadow DOM fallback via JavaScript
    try:
        el = driver.execute_script("""
            let renderer = document.querySelector('ytd-like-button-renderer');
            if (!renderer) return null;
            if (renderer.shadowRoot) {
                let btn = renderer.shadowRoot.querySelector('button, [role="button"]');
                if (btn) return btn;
            }
            return renderer.querySelector('button, [role="button"]');
        """)
        if el and el.is_displayed():
            label = (el.get_attribute("aria-label") or el.text or "").lower()
            pressed = el.get_attribute("aria-pressed") == "true"
            already_liked = pressed or any(w in label for w in ALREADY_LIKED_KEYWORDS)
            return el, already_liked
    except Exception:
        pass

    return None, False


# ── Account Switcher ─────────────────────────────────────────────

def switch_to_account(driver: WebDriver, account_row: Dict[str, Any]) -> bool:
    """
    Switch to the desired Brand Account on YouTube if not already active.
    If account_type is 'gmail_root', confirms root login.
    """
    acc_type = account_row.get("account_type", "gmail_root")
    if acc_type == "gmail_root":
        log("Account is Master Gmail (gmail_root). Using default profile identity.", "INFO")
        return True

    target_name = (account_row.get("switch_name") or account_row.get("channel_id") or "").strip()
    log(f"Switching to Brand Account: '{target_name}'", "INFO")

    try:
        safe_get(driver, "https://www.youtube.com/channel_switcher", timeout=30)
        time.sleep(random.uniform(2.0, 4.0))

        # Find account item in channel_switcher list
        items = driver.find_elements(
            By.CSS_SELECTOR,
            "ytd-account-item-renderer, paper-item, #channel-title, a[href*='/channel/']"
        )

        matched_element = None
        for it in items:
            txt = it.text.strip()
            if target_name and target_name.lower() in txt.lower():
                matched_element = it
                break

        if matched_element:
            log(f"Found Brand Account item '{target_name}'. Clicking to switch...", "INFO")
            human_click_element(driver, matched_element)
            time.sleep(random.uniform(3.0, 5.0))
            return True
        else:
            log(f"Warning: Channel item '{target_name}' not found on channel_switcher. Proceeding with active profile.", "WARN")
            return True
    except Exception as e:
        log(f"Error switching account: {e}", "WARN")
        return False


# ── Organic Interaction Stages ───────────────────────────────────

def warmup_before_sub(driver: WebDriver, mood: Any, dry_run: bool = False) -> None:
    """
    Stage 1: Warmup browsing before visiting target channel.
    Scrolls YouTube homepage, picks a random video, watches 35-65 seconds with natural drift.
    In dry_run mode, performs a fast 5s check.
    """
    log("Stage 1: Starting pre-sub organic warmup...", "INFO")
    safe_get(driver, "https://www.youtube.com", timeout=35)
    time.sleep(random.uniform(1.5, 3.0))

    # Scroll homepage naturally
    scroll_cycles = 1 if dry_run else random.randint(2, 4)
    for _ in range(scroll_cycles):
        cdp_scroll(driver, random.randint(300, 600))
        time.sleep(random.uniform(1.0, 2.0))

    # Pick a random video from homepage
    try:
        video_links = driver.find_elements(
            By.CSS_SELECTOR,
            "ytd-rich-item-renderer a#video-title-link, ytd-rich-item-renderer a#thumbnail"
        )
        if video_links:
            chosen = random.choice(video_links[:8])
            human_click_element(driver, chosen)
            time.sleep(random.uniform(1.5, 3.0))

            # Watch video for WARMUP_VIDEO_WATCH duration
            watch_duration = 5 if dry_run else random.randint(WARMUP_VIDEO_WATCH_MIN, WARMUP_VIDEO_WATCH_MAX)
            log(f"Watching warmup video for {watch_duration}s...", "INFO")

            elapsed = 0
            while elapsed < watch_duration:
                chunk = min(10, watch_duration - elapsed)
                time.sleep(chunk)
                elapsed += chunk
                skip_youtube_ads(driver)
                if random.random() < 0.3:
                    idle_drift(driver)

            log("Warmup video completed.", "SUCCESS")
    except Exception as e:
        log(f"Warmup video encounter non-fatal issue: {e}", "WARN")


def visit_target_channel_and_watch(driver: WebDriver, channel_url: str, dry_run: bool = False) -> Tuple[int, bool]:
    """
    Stage 2: Navigate to target channel, browse video list, watch 1 video.
    Uses zero-quota youtube_scraper to guarantee real video target even with custom channel layouts.
    Returns: (actual_watch_seconds, video_found)
    """
    log(f"Stage 2: Visiting target channel: {channel_url}", "INFO")
    safe_get(driver, channel_url, timeout=35)
    time.sleep(random.uniform(2.0, 3.5))

    # Scroll video tab / list
    cdp_scroll(driver, random.randint(300, 500))
    time.sleep(random.uniform(1.0, 2.0))

    # 1. Primary Strategy: Extract latest videos via Innertube scraper (Zero quota, no DOM drift)
    target_video_url = None
    target_video_title = None
    try:
        scraped_videos = get_channel_latest_videos(channel_url, limit=5)
        if scraped_videos:
            chosen = random.choice(scraped_videos)
            target_video_url = chosen.get("url")
            target_video_title = chosen.get("title")
            vid_id = chosen.get("video_id")
            log(f"Selected target video via Innertube: '{target_video_title}' ({target_video_url})", "INFO")

            # Try to click organically if present in current DOM
            video_el = None
            if vid_id:
                matched = driver.find_elements(By.CSS_SELECTOR, f"a[href*='{vid_id}']")
                for el in matched:
                    if el.is_displayed():
                        video_el = el
                        break

            if video_el:
                log("Found target video link on channel page. Clicking organically...", "INFO")
                human_click_element(driver, video_el)
            else:
                log("Target video link not in initial viewport. Navigating directly...", "INFO")
                safe_get(driver, target_video_url, timeout=35)

            time.sleep(random.uniform(2.0, 3.5))
    except Exception as e:
        log(f"Innertube video resolution non-fatal warning: {e}", "WARN")

    # 2. Secondary Strategy Fallback: Search DOM elements if primary strategy didn't find video
    if not target_video_url:
        video_selectors = [
            "ytd-rich-item-renderer a#video-title-link",
            "ytd-grid-video-renderer a#video-title",
            "ytd-video-renderer a#video-title",
            "a[href*='/watch?v=']",
        ]

        found_videos = []
        for sel in video_selectors:
            found_videos = driver.find_elements(By.CSS_SELECTOR, sel)
            if found_videos:
                break

        if not found_videos:
            log("No videos found on target channel page. Browsing channel header directly.", "WARN")
            wait_empty = 5 if dry_run else random.uniform(15.0, 25.0)
            time.sleep(wait_empty)
            return int(wait_empty), False

        target_video = random.choice(found_videos[:min(5, len(found_videos))])
        log("Selecting target video to watch from DOM...", "INFO")
        human_click_element(driver, target_video)
        time.sleep(random.uniform(2.0, 3.5))

    # 3. Watch target video for TARGET_VIDEO_WATCH duration
    watch_target = 8 if dry_run else random.randint(TARGET_VIDEO_WATCH_MIN, TARGET_VIDEO_WATCH_MAX)
    log(f"Watching target channel video for {watch_target}s (organic retention)...", "INFO")

    elapsed = 0
    while elapsed < watch_target:
        chunk = min(15, watch_target - elapsed)
        time.sleep(chunk)
        elapsed += chunk
        skip_youtube_ads(driver)
        if random.random() < 0.25:
            cdp_scroll(driver, random.randint(150, 350))
            time.sleep(random.uniform(1.0, 2.0))
            cdp_scroll(driver, random.randint(-350, -150))

    log(f"Finished watching target video ({elapsed}s watched).", "SUCCESS")
    return elapsed, True


def do_like_if_needed(driver: WebDriver, probability: float = LIKE_PROBABILITY) -> bool:
    """
    Stage 3: Like the currently playing video with configured probability.
    """
    if random.random() > probability:
        log("Skipping like action (probability roll bypassed).", "INFO")
        return False

    log("Stage 3: Attempting to like target video...", "INFO")
    btn, already_liked = find_like_button(driver)

    if already_liked:
        log("Video is already liked by this account.", "INFO")
        return True

    if btn is None:
        log("Like button could not be located on page.", "WARN")
        return False

    # Click like using human cursor
    clicked = human_click_element(driver, btn)
    if clicked:
        time.sleep(random.uniform(1.0, 2.0))
        log("Successfully clicked Like button.", "SUCCESS")
        return True
    return False


def do_subscribe(driver: WebDriver) -> bool:
    """
    Stage 4: Hover channel details, approach and click Subscribe button.
    Verifies that button transitions to 'Subscribed' state.
    """
    log("Stage 4: Executing Subscribe action...", "INFO")

    # Scroll slightly up towards metadata header
    cdp_scroll(driver, -200)
    time.sleep(random.uniform(1.0, 2.0))

    btn, already_subbed = find_subscribe_button(driver)

    if already_subbed:
        log("Channel is ALREADY subscribed by this account.", "SUCCESS")
        return True

    if btn is None:
        log("Error: Subscribe button not found via any selector or Shadow DOM.", "ERROR")
        return False

    # Move cursor and click subscribe
    clicked = human_click_element(driver, btn)
    if not clicked:
        log("Failed to click Subscribe button.", "ERROR")
        return False

    time.sleep(random.uniform(2.0, 4.0))

    # Verify subscription state
    _, verified = find_subscribe_button(driver)
    if verified:
        log("Confirmed: Channel state updated to SUBSCRIBED.", "SUCCESS")
        return True
    else:
        # Check text once more
        try:
            cur_text = (btn.text or btn.get_attribute("aria-label") or "").lower()
            if any(w in cur_text for w in ALREADY_SUBSCRIBED_KEYWORDS):
                log("Confirmed via button attribute: SUBSCRIBED.", "SUCCESS")
                return True
        except Exception:
            pass

    log("Warning: Click executed but 'Subscribed' state not verified in DOM.", "WARN")
    # Return True if click succeeded to avoid duplicate tries
    return True


def cooldown_browsing(driver: WebDriver, dry_run: bool = False) -> None:
    """
    Stage 5: Post-sub cooldown browsing.
    Visits homepage or a suggested video for 25-60s before closing session.
    In dry_run mode, performs a fast 2s check.
    """
    log("Stage 5: Starting post-sub cool-down browsing...", "INFO")
    try:
        cdp_scroll(driver, random.randint(300, 600))
        time.sleep(random.uniform(1.0, 2.0) if dry_run else random.uniform(2.0, 3.0))

        cooldown_sec = 2 if dry_run else random.randint(COOLDOWN_POST_SUB_MIN, COOLDOWN_POST_SUB_MAX)
        log(f"Cooling down session for {cooldown_sec}s...", "INFO")
        time.sleep(cooldown_sec)
        don_dep_tab_la(driver)
    except Exception as e:
        log(f"Cooldown browsing completed with note: {e}", "INFO")


# ── Session Orchestrator ─────────────────────────────────────────

def run_sub_session(
    gpm_profile_id: str,
    account_id: int,
    order_id: int,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Orchestrate full organic subscription session lifecycle:
      1. Lock account
      2. Open GPM Profile + CDP hooks
      3. Switch to Brand Account (if applicable)
      4. Warmup pre-sub viewing
      5. Visit target channel & watch target video
      6. Like video (60% probability)
      7. Subscribe to channel
      8. Post-sub cooldown browsing
      9. Clean browser shutdown & lock release
      10. Update cooldown and log attempt to DB
    """
    log(f"══════════════════════════════════════════════════", "INFO")
    log(f"Starting Sub Session: Order #{order_id} | Account #{account_id} | Profile {gpm_profile_id}", "INFO")
    log(f"Dry-run mode: {dry_run}", "INFO")
    log(f"══════════════════════════════════════════════════", "INFO")

    order = get_order(order_id)
    if not order:
        return {
            "order_id": order_id,
            "account_id": account_id,
            "sub_success": False,
            "fail_reason": f"Order #{order_id} does not exist",
        }

    channel_url = order["channel_url"]
    channel_id = order.get("channel_id") or channel_url

    account_row = get_account(account_id) or {}
    driver = None
    sub_success = False
    did_like = False
    watch_seconds = 0
    fail_reason = None

    try:
        with acquire_account_lock(account_id, locked_by="buff_sub"):
            # Step 1: Launch GPM profile
            driver, _ = open_profile_session(gpm_profile_id)
            if driver is None:
                raise RuntimeError(f"Could not initialize GPM browser for profile {gpm_profile_id}")

            mood = draw_session_mood()

            # Step 2: Switch account if Brand Account
            switch_to_account(driver, account_row)

            # Step 3: Warmup viewing
            warmup_before_sub(driver, mood, dry_run=dry_run)

            # Step 4: Visit target channel and watch video
            watch_seconds, _ = visit_target_channel_and_watch(driver, channel_url, dry_run=dry_run)

            # Step 5: Like video
            if dry_run:
                log("[DRY-RUN] Simulating Like button click (bypassed)", "INFO")
                did_like = True
            else:
                did_like = do_like_if_needed(driver, probability=LIKE_PROBABILITY)

            # Step 6: Subscribe to channel
            if dry_run:
                log("[DRY-RUN] Simulating Subscribe action (bypassed real click)", "INFO")
                sub_success = True
            else:
                sub_success = do_subscribe(driver)

            # Step 7: Post-sub cooldown
            cooldown_browsing(driver, dry_run=dry_run)

    except Exception as e:
        fail_reason = str(e)
        sub_success = False
        log(f"Sub session encountered error: {e}", "ERROR")

        if driver is not None:
            try:
                health_status, diag_msg = analyze_driver_health(driver)
                if health_status in FATAL_CONDITIONS:
                    fail_reason = f"[{health_status}] {diag_msg or fail_reason}"
                    if not dry_run:
                        suspend_account(account_id, reason=fail_reason)
                        check_cluster_health_and_protect(gpm_profile_id)
            except Exception as diag_err:
                log(f"Diagnostic error: {diag_err}", "WARN")

    finally:
        # Step 8: Clean browser shutdown
        if driver is not None:
            close_profile_session(driver, gpm_profile_id)

        # Step 9: Update cooldown & log database
        if sub_success and not dry_run:
            update_cooldown(account_id, days=COOLDOWN_DAYS_AFTER_SUB)

        if not dry_run:
            log_sub_attempt(
                order_id=order_id,
                account_id=account_id,
                channel_id=channel_id,
                watch_seconds=watch_seconds,
                did_like=did_like,
                sub_success=sub_success,
                fail_reason=fail_reason,
            )

    result = {
        "order_id": order_id,
        "account_id": account_id,
        "gpm_profile_id": gpm_profile_id,
        "channel_url": channel_url,
        "channel_id": channel_id,
        "sub_success": sub_success,
        "did_like": did_like,
        "watch_seconds": watch_seconds,
        "fail_reason": fail_reason,
        "dry_run": dry_run,
    }

    status_str = "SUCCESS" if sub_success else "FAILED"
    log(f"Sub Session Finished: Status = {status_str}", status_str)
    return result
