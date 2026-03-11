"""FastAPI application factory.

See docs/sub-specs/SS-25.md
"""

import logging
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from custom.api.routes import router
from custom.api.websocket import ws_manager

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Mounts API routes and serves React static files at root.
    """
    app = FastAPI(
        title="Crypto Signal Bot",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    app.include_router(router)

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await ws_manager.connect(ws)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            ws_manager.disconnect(ws)

    # Serve React static files (built at Docker build time)
    static_dir = os.path.join(os.path.dirname(__file__), "..", "..", "static")
    if os.path.isdir(static_dir):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    else:
        logger.warning("Static directory not found at %s — dashboard UI disabled", static_dir)

    return app
