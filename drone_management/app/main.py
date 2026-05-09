from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import command_service as cs_mod
from .config import settings  # noqa: F401  ensure env loaded
from .mavlink_link import MavlinkLink
from .routers import commands as commands_router
from .routers import cua as cua_router
from .routers import drones as drones_router
from .routers import ws as ws_router
from .telemetry_bus import bus


STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()

    await bus.start()

    link = MavlinkLink(
        bind_host=settings.mavlink_bind_host,
        bind_port=settings.mavlink_bind_port,
        drone_host=settings.drone_host,
        drone_port=settings.drone_port,
        gcs_system_id=settings.gcs_system_id,
        gcs_component_id=settings.gcs_component_id,
    )
    cs_mod.cmd_service = cs_mod.CommandService(link=link)

    def _on_message(msg):
        bus.ingest(msg)
        cs_mod.cmd_service.handle_message(msg)

    link.on_message = _on_message
    link.start(loop)

    app.state.link = link
    try:
        yield
    finally:
        link.stop()
        await bus.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="drone_management", lifespan=lifespan)
    app.include_router(drones_router.router)
    app.include_router(commands_router.router)
    app.include_router(ws_router.router)
    app.include_router(cua_router.router)

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

        @app.get("/", include_in_schema=False)
        async def index():
            return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/config", include_in_schema=False)
    async def get_client_config():
        return {
            "google_maps_api_key": settings.google_maps_api_key,
            "google_maps_map_id": settings.google_maps_map_id,
        }

    return app


app = create_app()
