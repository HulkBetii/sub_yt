# -*- coding: utf-8 -*-
"""
buff_sub.api.app — FastAPI Application Assembly with Lifespan & CORS
"""
import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

from ..logger import log
from ..config import LOG_FILE_PATH, BASE_DIR
from ..scheduler import start_scheduler, stop_scheduler
from .routes_orders import router as orders_router
from .routes_scheduler import router as scheduler_router
from .routes_system import router as system_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle manager.
    Automatically starts the autonomous scheduler on API startup
    and cleanly stops it on API shutdown.
    """
    log("[API] FastAPI service starting up. Initializing autonomous background scheduler...", "INFO")
    try:
        start_scheduler()
    except Exception as e:
        log(f"[API] Warning during scheduler autostart: {e}", "WARN")

    yield

    log("[API] FastAPI service shutting down. Terminating scheduler threads...", "INFO")
    try:
        stop_scheduler()
    except Exception as e:
        log(f"[API] Warning during scheduler shutdown: {e}", "WARN")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(
        title="buff-sub-yt Engine REST API",
        version="2.0.0",
        description="Autonomous YouTube Subscriber Growth Engine & Drip-Feed Scheduler Service",
        lifespan=lifespan,
    )

    # Enable CORS for React Dashboard integration (Phase 3)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routers
    app.include_router(orders_router)
    app.include_router(scheduler_router)
    app.include_router(system_router)

    # ── WebSocket Real-time Log Stream ───────────────────────────
    @app.websocket("/ws/logs")
    async def websocket_logs(websocket: WebSocket):
        await websocket.accept()
        last_pos = 0
        try:
            # Send initial 50 lines
            if os.path.exists(LOG_FILE_PATH):
                with open(LOG_FILE_PATH, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                    last_pos = f.tell()
                for line in lines[-50:]:
                    await websocket.send_text(line.rstrip())

            # Continuous poll loop
            while True:
                await asyncio.sleep(1.0)
                if os.path.exists(LOG_FILE_PATH):
                    with open(LOG_FILE_PATH, "r", encoding="utf-8", errors="replace") as f:
                        f.seek(last_pos)
                        new_lines = f.readlines()
                        last_pos = f.tell()
                    for line in new_lines:
                        if line.strip():
                            await websocket.send_text(line.rstrip())
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        except Exception as e:
            try:
                await websocket.send_text(f"[ERROR] WebSocket error: {e}")
            except Exception:
                pass

    # ── Mount Frontend Dashboard Static Bundle if built ─────────
    dist_dir = os.path.join(BASE_DIR, "dashboard", "dist")
    if os.path.isdir(dist_dir):
        app.mount("/", StaticFiles(directory=dist_dir, html=True), name="frontend")
        log(f"[API] Mounted Frontend Web Dashboard from {dist_dir}", "INFO")

    return app


app = create_app()

