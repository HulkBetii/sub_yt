# -*- coding: utf-8 -*-
"""
Logger module with console and file handlers, supporting UTF-8 on Windows.
"""
import os
import sys
import datetime
from .config import LOG_FILE_PATH

# Ensure console supports UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


_log_hooks = []


def register_log_hook(hook_fn):
    """Register hook for log streaming (e.g. WebSocket Server)."""
    if hook_fn not in _log_hooks:
        _log_hooks.append(hook_fn)


def log(message: str, level: str = "INFO"):
    """Output timestamped message to console, rotating log file, and registered hooks."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] [{level}] {message}"
    
    # Console output with simple coloring
    if level == "ERROR":
        prefix = "\033[91m"
    elif level == "WARN":
        prefix = "\033[93m"
    elif level == "SUCCESS":
        prefix = "\033[92m"
    else:
        prefix = "\033[0m"
    suffix = "\033[0m"
    
    try:
        print(f"{prefix}{formatted}{suffix}", flush=True)
    except UnicodeEncodeError:
        print(formatted.encode("ascii", "replace").decode("ascii"), flush=True)

    # Append to log file
    try:
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
    except Exception:
        pass

    # Dispatch to registered hooks
    for hook in _log_hooks:
        try:
            hook(formatted)
        except Exception:
            pass
