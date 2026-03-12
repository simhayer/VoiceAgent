"""Twilio call handling: TwiML webhook + WebSocket for Media Streams."""

import logging

from fastapi import APIRouter, Depends, Request, WebSocket
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.services.tenant_service import resolve_tenant_by_phone
from app.voice.pipeline import run_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calls", tags=["calls"])


@router.post("/incoming")
async def incoming_call(request: Request, db: AsyncSession = Depends(get_db)):
    """Twilio hits this when a call comes in. Returns TwiML to start a Media Stream.

    Resolves the tenant from the called (To) number and passes tenant_id
    as a custom parameter into the WebSocket stream.
    """
    form = await request.form()
    called_number = form.get("To", "")
    caller_phone = form.get("From", "")

    tenant = await resolve_tenant_by_phone(db, called_number)
    if not tenant:
        logger.warning("No tenant found for called number %s", called_number)
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>We're sorry, this number is not currently in service. Goodbye.</Say>
    <Hangup/>
</Response>"""
        return Response(content=twiml, media_type="application/xml")

    server_url = settings.server_url.replace("http://", "wss://").replace("https://", "wss://")
    stream_url = f"{server_url}/calls/stream"

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{stream_url}">
            <Parameter name="callerPhone" value="{caller_phone}" />
            <Parameter name="tenantId" value="{tenant.id}" />
        </Stream>
    </Connect>
</Response>"""

    logger.info("Incoming call for tenant %s (%s) — directing to stream", tenant.name, tenant.id)
    return Response(content=twiml, media_type="application/xml")


@router.websocket("/stream")
async def media_stream(websocket: WebSocket):
    """Bidirectional WebSocket endpoint for Twilio Media Streams.

    Twilio connects here after the TwiML <Stream> instruction.
    The voice pipeline handles all audio processing.
    """
    logger.info("New Twilio Media Stream WebSocket connection")
    await run_pipeline(websocket)
