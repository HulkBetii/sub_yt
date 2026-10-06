# -*- coding: utf-8 -*-
"""
youtube_scraper.py — Zero-Quota, Anti-DOM-Drift YouTube Video Extractor
Fetches real, active video URLs from any target channel without official API quota
or heavy Selenium rendering, supporting both classic 'videoRenderer' and modern 2024-2026 'lockupViewModel' schemas.
"""
import re
import time
import json
from typing import List, Dict, Any, Optional, Tuple
import requests

from .logger import log

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# In-memory LRU-like cache: channel_url -> (timestamp, List[videos])
_VIDEO_CACHE: Dict[str, Tuple[float, List[Dict[str, str]]]] = {}
_CACHE_TTL_SECONDS = 600.0  # 10 minutes cache


def normalize_channel_url(channel_input: str) -> str:
    """
    Normalize various channel formats (@handle, short URL, full URL)
    into a canonical https://www.youtube.com/@handle/videos target.
    """
    raw = (channel_input or "").strip()
    if not raw:
        return ""

    if raw.startswith("@"):
        return f"https://www.youtube.com/{raw}/videos"

    if not raw.startswith("http://") and not raw.startswith("https://"):
        if raw.startswith("youtube.com") or raw.startswith("www.youtube.com"):
            raw = f"https://{raw}"
        else:
            raw = f"https://www.youtube.com/@{raw}"

    # Strip query parameters and trailing slash
    base = raw.split("?")[0].rstrip("/")

    # If it ends with /videos, /shorts, /featured, strip and re-append /videos
    for suffix in ["/videos", "/shorts", "/featured", "/streams"]:
        if base.endswith(suffix):
            base = base[:-len(suffix)]
            break

    return f"{base}/videos"


def _search_dict(partial: Any, search_key: str):
    """Recursively search for all occurrences of search_key in nested dict/list."""
    if isinstance(partial, dict):
        for k, v in partial.items():
            if k == search_key:
                yield v
            elif isinstance(v, (dict, list)):
                yield from _search_dict(v, search_key)
    elif isinstance(partial, list):
        for item in partial:
            if isinstance(item, (dict, list)):
                yield from _search_dict(item, search_key)


def get_channel_latest_videos(
    channel_url: str,
    limit: int = 5,
    timeout: float = 12.0,
    force_refresh: bool = False,
) -> List[Dict[str, str]]:
    """
    Extract latest public videos for a YouTube channel via Innertube web endpoint.
    Zero-quota, bypasses frontend browser rendering changes.
    Returns:
        List of dicts: [{'video_id': '...', 'title': '...', 'url': '...'}]
    """
    normalized_url = normalize_channel_url(channel_url)
    if not normalized_url:
        log(f"Invalid channel URL provided: '{channel_url}'", "WARN")
        return []

    # Check cache
    now = time.time()
    if not force_refresh and normalized_url in _VIDEO_CACHE:
        cached_time, cached_items = _VIDEO_CACHE[normalized_url]
        if now - cached_time < _CACHE_TTL_SECONDS and len(cached_items) > 0:
            log(f"Retrieved {len(cached_items[:limit])} videos from cache for {normalized_url}", "INFO")
            return cached_items[:limit]

    log(f"Fetching latest videos from YouTube Innertube: {normalized_url}", "INFO")

    session = requests.Session()
    session.headers.update({
        "User-Agent": _DEFAULT_USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    })

    results: List[Dict[str, str]] = []

    try:
        resp = session.get(normalized_url, timeout=timeout)
        if resp.status_code != 200:
            log(f"YouTube returned HTTP {resp.status_code} for {normalized_url}", "WARN")
            return []

        html = resp.text

        # 1. Parse ytInitialData payload from HTML
        match = re.search(r"var\s+ytInitialData\s*=\s*({.+?});\s*</script>", html, re.DOTALL)
        if not match:
            match = re.search(r"window\[\"ytInitialData\"\]\s*=\s*({.+?});\s*</script>", html, re.DOTALL)

        if not match:
            log(f"ytInitialData payload not found in channel page HTML: {normalized_url}", "WARN")
            return []

        data = json.loads(match.group(1))

        # 2. Extract videos: Support modern 'lockupViewModel' (2024-2026)
        for item in _search_dict(data, "lockupViewModel"):
            vid_id = item.get("contentId")
            if vid_id and isinstance(vid_id, str) and len(vid_id) >= 8:
                # Extract title
                meta = item.get("metadata", {}).get("lockupMetadataViewModel", {})
                title_obj = meta.get("title", {})
                title = title_obj.get("content") or "YouTube Video"

                if not any(r["video_id"] == vid_id for r in results):
                    results.append({
                        "video_id": vid_id,
                        "title": title,
                        "url": f"https://www.youtube.com/watch?v={vid_id}",
                    })
                    if len(results) >= limit:
                        break

        # 3. Fallback: Support classic 'videoRenderer'
        if not results:
            for item in _search_dict(data, "videoRenderer"):
                vid_id = item.get("videoId")
                if vid_id and isinstance(vid_id, str):
                    title_runs = item.get("title", {}).get("runs", [])
                    title = title_runs[0].get("text") if title_runs else "YouTube Video"

                    if not any(r["video_id"] == vid_id for r in results):
                        results.append({
                            "video_id": vid_id,
                            "title": title,
                            "url": f"https://www.youtube.com/watch?v={vid_id}",
                        })
                        if len(results) >= limit:
                            break

        if results:
            log(f"Successfully scraped {len(results)} videos for {normalized_url} (Top: '{results[0]['title']}')", "SUCCESS")
            _VIDEO_CACHE[normalized_url] = (now, results)
        else:
            log(f"No video items extracted from {normalized_url}. Channel may be empty or restricted.", "WARN")

    except Exception as e:
        log(f"Error scraping YouTube channel videos ({channel_url}): {e}", "WARN")

    finally:
        session.close()

    return results[:limit]
