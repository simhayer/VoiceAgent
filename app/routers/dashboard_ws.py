"""WebSocket endpoint for the live dashboard UI."""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth import get_user_from_token
from app.database import async_session
from app.services.pubsub import listen, _pool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.websocket("/ws")
async def dashboard_ws(websocket: WebSocket):
    """Stream live call events to a connected dashboard client.

    Uses the shared Redis subscriber — no per-client Redis connections.
    Messages are fanned out in-memory via asyncio queues.
    If Redis is unavailable, the WS stays open and waits for it.
    """
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="Missing auth token")
        return

    try:
        async with async_session() as db:
            user = await get_user_from_token(token, db)
    except Exception:
        await websocket.close(code=1008, reason="Invalid auth token")
        return

    await websocket.accept()
    logger.info("Dashboard client connected for tenant %s", user.tenant_id)

    try:
        # Wait for Redis to become available (check every 10s)
        while _pool() is None:
            await asyncio.sleep(10)

        async for raw_data in listen():
            try:
                event = json.loads(raw_data)
            except json.JSONDecodeError:
                continue

            if event.get("tenant_id") != user.tenant_id:
                continue

            await websocket.send_text(json.dumps(event))
    except WebSocketDisconnect:
        logger.info("Dashboard client disconnected")
    except Exception:
        logger.exception("Dashboard WS error")
