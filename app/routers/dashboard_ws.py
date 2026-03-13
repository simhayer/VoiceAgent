"""WebSocket endpoint for the live dashboard UI."""

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth import get_user_from_token
from app.database import async_session
from app.services.pubsub import subscribe

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.websocket("/ws")
async def dashboard_ws(websocket: WebSocket):
    """Stream live call events to a connected dashboard client.

    Subscribes to the Redis `dashboard_events` channel and forwards
    every message to the browser over WebSocket.
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
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue

                if event.get("tenant_id") != user.tenant_id:
                    continue

                await websocket.send_text(json.dumps(event))
    except WebSocketDisconnect:
        logger.info("Dashboard client disconnected")
    except Exception:
        logger.exception("Dashboard WS error")
    finally:
        await ps.unsubscribe()
        await ps.aclose()
