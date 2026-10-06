# -*- coding: utf-8 -*-
"""
Central Configuration for buff-sub-yt Engine
All operational thresholds, file paths, and anti-detection parameters.
"""
import os

# ── Paths ────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
SHARED_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "shared"))

SHARED_DB_PATH = os.path.join(SHARED_DIR, "account_pool.db")
LOCAL_DB_PATH = os.path.join(DATA_DIR, "buff_sub.db")
LOG_FILE_PATH = os.path.join(LOGS_DIR, "buff_sub.log")
LOG_FILE = LOG_FILE_PATH

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(SHARED_DIR, exist_ok=True)

# ── Ad Blocker Domains (used by tab_guard.py) ────────────────────
DOMAINS_QUANG_CAO = [
    "googleadservices.com", "googlesyndication.com", "doubleclick.net",
    "pagead2.googlesyndication.com", "adservice.google.com", "taboola.com",
    "outbrain.com", "mgid.com", "revcontent.com", "contentad.net",
    "adnxs.com", "adsrvr.org", "rubiconproject.com", "openx.net",
    "pubmatic.com", "casalemedia.com", "criteo.com", "adcolony.com",
    "applovin.com", "mopub.com", "inmobi.com", "amazon-adsystem.com",
    "media.net", "zedo.com", "advertising.com", "adblade.com",
    "adform.net", "smartadserver.com", "bidswitch.net", "lijit.com",
    "sovrn.com", "rhythmone.com", "sharethrough.com", "spotxchange.com",
    "tremorvideo.com", "yieldmo.com", "popads.net", "popcash.net",
    "propellerads.com", "adcash.com", "hilltopads.net", "trafficjunky.com",
    "clickadu.com", "googletagmanager.com", "hotjar.com", "mouseflow.com",
]

# ── GPM Login API ────────────────────────────────────────────────
GPM_API_URL = "http://127.0.0.1:19995"
GPM_BROWSER_DIR = r"C:\GPM\GPMLogin\gpm_browser"
GPM_ADDITIONAL_ARGS = "--lang=en-US,en --disable-notifications"
REQUIRED_PROFILE_PREFIX = "sub_yt-"
REQUIRED_PROFILE_REGEX = r"^sub_yt-\d+$"

# ── Concurrency & Resource Limits ────────────────────────────────
MAX_PARALLEL_PROFILES = 2       # Safe limit for 32GB RAM workstation
PROFILE_LOCK_TIMEOUT_MIN = 30   # Auto-expire locks after 30 minutes

# ── Account Trust & Cooldown Guardrails ──────────────────────────
WARMUP_MIN_DAYS = 14            # Minimum nurture days for Brand Accounts
WARMUP_MIN_VIDEOS = 30          # Minimum videos watched before 'ready'
COOLDOWN_DAYS_AFTER_SUB = 3     # Rest duration for account after subscribing
MAX_SUBS_PER_ACCOUNT_MONTH = 8  # Safe monthly ceiling per account

# ── Anti-Clustering Constraints ──────────────────────────────────
MAX_SUBS_PER_CHANNEL_PER_HOUR = 3    # Anti-spike velocity limit
SAME_GMAIL_COOLDOWN_HOURS = 48       # Gap before another account from same Gmail subs

# ── Organic Sub Session Timing (Seconds) ─────────────────────────
WARMUP_VIDEO_WATCH_MIN = 35     # Watch 1 random home video before channel
WARMUP_VIDEO_WATCH_MAX = 65

TARGET_VIDEO_WATCH_MIN = 90     # Watch target video duration
TARGET_VIDEO_WATCH_MAX = 240

LIKE_PROBABILITY = 0.60         # 60% probability to like video before subscribing
COOLDOWN_POST_SUB_MIN = 25      # Watch random video afterwards before closing
COOLDOWN_POST_SUB_MAX = 60

# ── Drip-Feed & Autonomous Scheduler ─────────────────────────────
DRIP_FEED_ENABLED = True             # Enable S-Curve capacity scaling
SCHEDULER_TICK_INTERVAL_MINUTES = 15 # Routine job trigger interval
API_HOST = "127.0.0.1"               # FastAPI REST host
API_PORT = 8000                      # FastAPI REST port

