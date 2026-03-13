"""Voice pipeline: bridges Twilio Media Streams <-> OpenAI Realtime API.

Audio flows with zero conversion (both sides use g711 mulaw 8kHz).
OpenAI handles VAD, interruption, STT, LLM reasoning, and TTS in one WebSocket.
"""

import asyncio
import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

from app.config import settings
from app.database import async_session
from app.services.call_log_service import persist_call_ended, persist_call_started, persist_message
from app.services.office_context import get_all_office_info
from app.services.pubsub import publish_event
from app.services.tenant_service import get_tenant_by_id
from app.voice.realtime import RealtimeSession
from app.voice.session import CallSession

logger = logging.getLogger(__name__)

DEFAULT_GREETING = "Hi, thank you for calling! How can I help you today?"


async def run_pipeline(websocket: WebSocket):
    """Main entry point: handles one Twilio Media Stream WebSocket connection."""
    await websocket.accept()
    session = CallSession(twilio_ws=websocket)
    realtime: RealtimeSession | None = None

    try:
        realtime = await _receive_loop(websocket, session)
    except WebSocketDisconnect:
        logger.info("Twilio WebSocket disconnected for call %s", session.call_sid)
    except Exception:
        logger.exception("Pipeline error for call %s", session.call_sid)
    finally:
        session.is_active = False
        if realtime:
            await realtime.close()
        if session.call_sid:
            await publish_event("call_ended", session.call_sid, tenant_id=session.tenant_id)
            await persist_call_ended(session.call_sid)
        logger.info("Pipeline cleaned up for call %s", session.call_sid)


async def _receive_loop(websocket: WebSocket, session: CallSession) -> RealtimeSession | None:
    """Receive messages from Twilio and bridge to OpenAI Realtime.

    Returns the RealtimeSession so the caller can clean it up.
    """
    realtime: RealtimeSession | None = None

    while session.is_active:
        try:
            raw = await asyncio.wait_for(
                websocket.receive_text(),
                timeout=settings.call_inactivity_timeout_s,
            )
        except asyncio.TimeoutError:
            if realtime and realtime._is_open:
                await realtime.send_text_message(
                    "Are you still there? I haven't heard anything for a bit."
                )
                session.touch_activity()
                try:
                    raw = await asyncio.wait_for(
                        websocket.receive_text(),
                        timeout=settings.call_inactivity_timeout_s,
                    )
                except asyncio.TimeoutError:
                    logger.info("Double inactivity timeout — ending call %s", session.call_sid)
                    if realtime and realtime._is_open:
                        await realtime.send_text_message(
                            "It seems like you've stepped away. Feel free to call back anytime. Goodbye!"
                        )
                        await asyncio.sleep(3.0)
                    session.is_active = False
                    break
                except WebSocketDisconnect:
                    break
            else:
                session.is_active = False
                break
        except WebSocketDisconnect:
            break

        session.touch_activity()
        data = json.loads(raw)
        event = data.get("event")

        if event == "start":
            start_data = data.get("start", {})
            session.stream_sid = start_data.get("streamSid", "")
            session.call_sid = start_data.get("callSid", "")
            custom = start_data.get("customParameters", {})
            session.caller_phone = custom.get("callerPhone", "")
            session.tenant_id = custom.get("tenantId", "")
            logger.info(
                "Call started: callSid=%s streamSid=%s tenant=%s",
                session.call_sid,
                session.stream_sid,
                session.tenant_id,
            )

            asyncio.create_task(
                publish_event(
                    "call_started",
                    session.call_sid,
                    caller_phone=session.caller_phone,
                    tenant_id=session.tenant_id,
                )
            )
            asyncio.create_task(
                persist_call_started(session.call_sid, session.caller_phone, session.tenant_id)
            )

            await _load_tenant_context(session)

            realtime = await _create_realtime_session(session)
            greeting = session.tenant_greeting or DEFAULT_GREETING
            await realtime.send_greeting(greeting)

            asyncio.create_task(
                publish_event(
                    "agent_transcript",
                    session.call_sid,
                    text=greeting,
                    tenant_id=session.tenant_id,
                )
            )
            asyncio.create_task(persist_message(session.call_sid, "assistant", greeting))

        elif event == "media" and realtime:
            payload = data["media"]["payload"]
            await realtime.send_audio(payload)

        elif event == "stop":
            logger.info("Twilio stream stopped for call %s", session.call_sid)
            session.is_active = False
            break

    return realtime


async def _create_realtime_session(session: CallSession) -> RealtimeSession:
    """Set up the OpenAI Realtime session with callbacks wired to Twilio + logging."""

    async def on_audio_delta(base64_audio: str):
        await session.send_audio_to_twilio(base64_audio)

    async def on_speech_started():
        await session.clear_twilio_audio()

    async def on_transcript(role: str, text: str):
        event_name = "user_transcript" if role == "user" else "agent_transcript"
        asyncio.create_task(
            publish_event(
                event_name,
                session.call_sid,
                text=text,
                tenant_id=session.tenant_id,
            )
        )
        asyncio.create_task(persist_message(session.call_sid, role, text))

    async def on_response_done():
        pass

    rt = RealtimeSession(
        tenant_id=session.tenant_id,
        tenant_name=session.tenant_name,
        office_info=session.tenant_office_info,
        emergency_phone=session.tenant_emergency_phone,
        transfer_phone=session.tenant_transfer_phone,
        on_audio_delta=on_audio_delta,
        on_speech_started=on_speech_started,
        on_transcript=on_transcript,
        on_response_done=on_response_done,
    )
    await rt.connect()
    await rt.configure_session()
    return rt


async def _load_tenant_context(session: CallSession) -> None:
    """Load tenant details and office config from the database into the session."""
    async with async_session() as db:
        tenant = await get_tenant_by_id(db, session.tenant_id)
        if not tenant:
            logger.warning("Tenant %s not found during pipeline init", session.tenant_id)
            session.tenant_name = "Our Office"
            return

        session.tenant_name = tenant.name
        session.tenant_greeting = tenant.greeting_message or f"Hi, thank you for calling {tenant.name}! How can I help you today?"
        session.tenant_emergency_phone = tenant.emergency_phone
        session.tenant_transfer_phone = tenant.transfer_phone

        office_entries = await get_all_office_info(db, session.tenant_id)
        session.tenant_office_info = {e["key"]: e["value"] for e in office_entries}
