"""
WebSocket Manager for real-time analysis progress.

Provides real-time progress updates to the frontend during audio analysis.
Each analysis job broadcasts progress events to connected clients.

Events:
- analysis:started    → { report_id, filename, stage: "started" }
- analysis:progress   → { report_id, stage, progress_pct, message }
- analysis:completed  → { report_id, severity, risk_score, stage: "completed" }
- analysis:failed     → { report_id, error, stage: "failed" }
"""

import logging
import asyncio
import json
from typing import Dict, Set, Any, Optional
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections for real-time progress updates.

    Clients connect to /ws/progress and receive updates for all active analyses.
    Optionally, clients can subscribe to a specific report_id.
    """

    def __init__(self):
        # All active connections
        self._connections: Set[WebSocket] = set()
        # Connections subscribed to specific report IDs
        self._subscriptions: Dict[int, Set[WebSocket]] = {}
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, report_id: Optional[int] = None):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
            if report_id is not None:
                if report_id not in self._subscriptions:
                    self._subscriptions[report_id] = set()
                self._subscriptions[report_id].add(websocket)
        logger.debug(f"WebSocket connected (total: {len(self._connections)})")

    async def disconnect(self, websocket: WebSocket):
        """Remove a disconnected WebSocket."""
        async with self._lock:
            self._connections.discard(websocket)
            # Remove from all subscriptions
            for report_id in list(self._subscriptions.keys()):
                self._subscriptions[report_id].discard(websocket)
                if not self._subscriptions[report_id]:
                    del self._subscriptions[report_id]
        logger.debug(f"WebSocket disconnected (total: {len(self._connections)})")

    async def broadcast(self, event: str, data: Dict[str, Any]):
        """Broadcast an event to all connected clients."""
        message = json.dumps({"event": event, "data": data, "timestamp": datetime.now(timezone.utc).isoformat()})
        disconnected = set()
        for ws in self._connections.copy():
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.add(ws)
        # Clean up disconnected
        for ws in disconnected:
            await self.disconnect(ws)

    async def send_to_report(self, report_id: int, event: str, data: Dict[str, Any]):
        """Send an event to clients subscribed to a specific report."""
        message = json.dumps({"event": event, "data": data, "timestamp": datetime.now(timezone.utc).isoformat()})
        subscribers = self._subscriptions.get(report_id, set()).copy()
        # Also send to all general connections
        all_targets = subscribers | self._connections.copy()
        disconnected = set()
        for ws in all_targets:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.add(ws)
        for ws in disconnected:
            await self.disconnect(ws)

    @property
    def active_connections(self) -> int:
        return len(self._connections)


# ── Global instance ───────────────────────────────────────────────────────────
manager = ConnectionManager()


# ── Progress notification helpers (called from background tasks) ───────────────

# Since background tasks run in threads, we need a way to push events
# to the async WebSocket manager. We use a simple queue approach.

_progress_queue: asyncio.Queue = None


def _get_or_create_queue() -> Optional[asyncio.Queue]:
    """Get the progress queue (created on first use in the event loop)."""
    global _progress_queue
    return _progress_queue


def init_progress_queue(loop: asyncio.AbstractEventLoop):
    """Initialize the progress queue (called during app startup)."""
    global _progress_queue
    _progress_queue = asyncio.Queue()


def notify_progress(
    report_id: int,
    stage: str,
    progress_pct: int = 0,
    message: str = "",
    severity: Optional[str] = None,
    risk_score: Optional[float] = None,
    error: Optional[str] = None,
):
    """
    Thread-safe progress notification.
    Called from background analysis threads to push updates to WebSocket clients.

    This queues the event for the async event loop to process.
    """
    event_data = {
        "report_id": report_id,
        "stage": stage,
        "progress_pct": progress_pct,
        "message": message,
    }

    if stage == "completed":
        event_name = "analysis:completed"
        event_data["severity"] = severity
        event_data["risk_score"] = risk_score
    elif stage == "failed" or error:
        event_name = "analysis:failed"
        event_data["error"] = error or "Unknown error"
    elif stage == "started":
        event_name = "analysis:started"
    else:
        event_name = "analysis:progress"

    # Try to push to the async queue
    queue = _get_or_create_queue()
    if queue is not None:
        try:
            queue.put_nowait({"event": event_name, "data": event_data, "report_id": report_id})
        except asyncio.QueueFull:
            logger.warning(f"WebSocket progress queue full, dropping event for #{report_id}")
    else:
        logger.debug(f"WebSocket queue not initialized, skipping progress for #{report_id}")


async def process_progress_queue():
    """
    Background coroutine that drains the progress queue and broadcasts events.
    Should be started as an asyncio task during app startup.
    """
    global _progress_queue
    if _progress_queue is None:
        init_progress_queue(asyncio.get_event_loop())

    while True:
        try:
            item = await _progress_queue.get()
            report_id = item.get("report_id")
            event = item.get("event")
            data = item.get("data")

            if report_id:
                await manager.send_to_report(report_id, event, data)
            else:
                await manager.broadcast(event, data)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"WebSocket progress queue error: {e}")
            await asyncio.sleep(0.1)
