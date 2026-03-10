"""Twilio call handling: TwiML webhook + WebSocket for Media Streams."""

import logging

from fastapi import APIRouter, Request, WebSocket
from fastapi.responses import Response

from app.config import settings
from app.voice.pipeline import run_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calls", tags=["calls"])


@router.post("/incoming")
async def incoming_call(request: Request):
    """Twilio hits this when a call comes in. Returns TwiML to start a Media Stream.

    Configure this URL as the webhook for your Twilio phone number.
    """
    server_url = settings.server_url.replace("http://", "wss://").replace("https://", "wss://")
    stream_url = f"{server_url}/calls/stream"

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{stream_url}">
            <Parameter name="callerPhone" value="{{{{From}}}}" />
        </Stream>
    </Connect>
</Response>"""

    logger.info("Incoming call — directing to stream at %s", stream_url)
    return Response(content=twiml, media_type="application/xml")


@router.websocket("/stream")
async def media_stream(websocket: WebSocket):
    """Bidirectional WebSocket endpoint for Twilio Media Streams.

    Twilio connects here after the TwiML <Stream> instruction.
    The voice pipeline handles all audio processing.
    """
    logger.info("New Twilio Media Stream WebSocket connection")
    await run_pipeline(websocket)
