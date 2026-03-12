"""WebSocket endpoint for the live dashboard UI."""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.pubsub import subscribe

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.websocket("/ws")
async def dashboard_ws(websocket: WebSocket):
    """Stream live call events to a connected dashboard client.

    Subscribes to the Redis `dashboard_events` channel and forwards
    every message to the browser over WebSocket.
    """
    await websocket.accept()
    logger.info("Dashboard client connected")

    ps = await subscribe()
    if ps is None:
        # Redis unavailable — tell the client and close gracefully
        await websocket.send_json({"type": "error", "message": "Event bus unavailable"})
        await websocket.close()
        return

    try:
        async for raw_message in ps.listen():
            if raw_message["type"] != "message":
                continue
            data = raw_message.get("data")
            if isinstance(data, str):
                await websocket.send_text(data)
    except WebSocketDisconnect:
        logger.info("Dashboard client disconnected")
    except Exception:
        logger.exception("Dashboard WS error")
    finally:
        await ps.unsubscribe()
        await ps.aclose()
