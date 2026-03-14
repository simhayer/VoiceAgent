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
from app.services import active_calls, tenant_runtime
from app.services.call_log_service import persist_call_ended, persist_call_started, persist_message
from app.services.pubsub import publish_event
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
        if session.call_sid:
            active_calls.unregister_call(session.call_sid)
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
            if session.call_sid:
                active_calls.register_call(
                    session.call_sid,
                    session.tenant_id,
                    session,
                    realtime,
                )
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

    async def on_token_delta(delta: str):
        """Stream word-by-word transcript deltas to the dashboard."""
        asyncio.create_task(
            publish_event(
                "agent_token_delta",
                session.call_sid,
                delta=delta,
                tenant_id=session.tenant_id,
            )
        )

    async def on_tool_call(tool_call_id: str, tool_name: str, status: str, result: str):
        """Notify the dashboard of tool start/end events."""
        event_type = "tool_start" if status == "start" else "tool_end"
        payload: dict = {
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "tenant_id": session.tenant_id,
        }
        if status == "start":
            try:
                payload["tool_args"] = json.loads(result)
            except Exception:
                payload["tool_args"] = {}
        else:
            payload["tool_result"] = result
            # If this was a book_appointment tool, also emit a special event
            if tool_name == "book_appointment":
                try:
                    booking = json.loads(result)
                    logger.info("book_appointment result: success=%s data=%s", booking.get("success"), result)
                    if booking.get("success"):
                        asyncio.create_task(
                            publish_event(
                                "appointment_booked",
                                session.call_sid,
                                tenant_id=session.tenant_id,
                                appointment={k: v for k, v in booking.items() if k != "success"},
                            )
                        )
                except Exception:
                    logger.exception("Failed to parse book_appointment result")

        asyncio.create_task(
            publish_event(event_type, session.call_sid, **payload)
        )
        # Persist tool messages in call log
        if status == "start":
            try:
                tool_args_dict = json.loads(result)
            except Exception:
                tool_args_dict = {}
            asyncio.create_task(
                persist_message(
                    session.call_sid,
                    event_type,
                    f"Using tool: {tool_name}",
                    tool_name=tool_name,
                    tool_args=tool_args_dict,
                )
            )
        else:
            asyncio.create_task(
                persist_message(
                    session.call_sid,
                    event_type,
                    f"Used tool: {tool_name}",
                    tool_name=tool_name,
                )
            )

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
        openai_realtime_model=session.tenant_openai_model,
        openai_realtime_voice=session.tenant_openai_voice,
        system_prompt_override=session.tenant_system_prompt_override,
        on_token_delta=on_token_delta,
        on_tool_call=on_tool_call,
    )
    await rt.connect()
    await rt.configure_session()
    return rt


async def _load_tenant_context(session: CallSession) -> None:
    """Load tenant details, agent settings, and office config from the database into the session."""
    config = tenant_runtime.get_tenant_config(session.tenant_id)
    if not config:
        async with async_session() as db:
            config = await tenant_runtime.refresh_tenant(db, session.tenant_id)

    if not config:
        logger.warning("Tenant %s not found during pipeline init", session.tenant_id)
        session.tenant_name = "Our Office"
        return

    session.apply_runtime_config(config)
    if not session.tenant_greeting:
        session.tenant_greeting = (
            f"Hi, thank you for calling {session.tenant_name}! How can I help you today?"
        )
