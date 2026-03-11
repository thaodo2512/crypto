"""WebSocket manager for live dashboard updates.

See docs/sub-specs/SS-25.md
"""

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections and broadcasts updates."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        """Accept and register a WebSocket connection."""
        await ws.accept()
        self._connections.add(ws)
        logger.info("WebSocket connected (%d total)", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        """Remove a WebSocket connection."""
        self._connections.discard(ws)
        logger.info("WebSocket disconnected (%d total)", len(self._connections))

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send a JSON message to all connected clients."""
        if not self._connections:
            return
        data = json.dumps(message)
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.discard(ws)

    def broadcast_sync(self, message: dict[str, Any], loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Thread-safe broadcast (called from scheduler threads).

        Uses the same pattern as Telegram's broadcast_sync.
        """
        if not self._connections:
            return
        if loop is None:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                return
        try:
            asyncio.run_coroutine_threadsafe(self.broadcast(message), loop)
        except Exception as e:
            logger.warning("WebSocket broadcast_sync failed: %s", e)

    @property
    def connection_count(self) -> int:
        """Number of active connections."""
        return len(self._connections)


ws_manager = ConnectionManager()
