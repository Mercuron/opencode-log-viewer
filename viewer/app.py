from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import Settings, get_settings
from .db import open_db
from .eventbus import SessionEventBus
from .ingest import IngestWorker
from .migrations import apply_migrations
from .retention import retention_loop
from .routes import router

logging.basicConfig(level=logging.INFO)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        conn = open_db(settings)
        applied = apply_migrations(conn)
        if applied:
            logging.getLogger("viewer").info("applied %d migration(s)", applied)

        bus = SessionEventBus()
        worker = IngestWorker(conn, settings, on_written=bus.publish)
        worker.start()

        app.state.settings = settings
        app.state.conn = conn
        app.state.bus = bus
        app.state.worker = worker
        app.state.ready = True

        retention_task = None
        if os.environ.get("VIEWER_DISABLE_RETENTION") != "1":
            import asyncio

            retention_task = asyncio.create_task(retention_loop(conn, settings))

        try:
            yield
        finally:
            await worker.stop()
            if retention_task:
                retention_task.cancel()
            conn.close()

    app = FastAPI(title="opencode-log-viewer", lifespan=lifespan)
    app.include_router(router, prefix="/api/v1")

    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.is_dir() and any(static_dir.iterdir()):
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


app = create_app()
