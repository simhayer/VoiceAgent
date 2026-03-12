"""Voice pipeline orchestrator: wires Twilio <-> Deepgram STT <-> LangGraph Agent <-> Cartesia TTS.

Streams LLM tokens directly into TTS for low time-to-first-audio.
"""

import asyncio
import json
import logging
import random
import time

from fastapi import WebSocket, WebSocketDisconnect

from app.agent.graph import stream_message
from app.config import settings
from app.database import async_session
from app.services.call_log_service import persist_call_ended, persist_call_started, persist_message
from app.services.office_context import get_all_office_info
from app.services.pubsub import publish_event
from app.services.tenant_service import get_tenant_by_id
from app.voice.audio import twilio_payload_to_deepgram
from app.voice.interruption import handle_interruption
from app.voice.session import CallSession
from app.voice.stt import DeepgramSTT
from app.voice.tts import CartesiaTTS

logger = logging.getLogger(__name__)

DEFAULT_GREETING = "Hi, thank you for calling! How can I help you today?"

FILLER_PHRASES: dict[str, list[str]] = {
    "check_availability": [
        "Let me check the schedule.",
        "One sec, pulling up the calendar.",
        "Let me see what's open.",
    ],
    "book_appointment": [
        "Got it, booking that now.",
        "One moment while I lock that in.",
    ],
    "lookup_patient": [
        "Let me pull up your info.",
        "One sec, looking you up.",
    ],
    "get_office_info": [
        "Good question — one sec.",
        "Let me grab that for you.",
    ],
    "_default": [
        "One moment, please.",
        "Sure, give me just a second.",
        "Hang on one sec.",
    ],
}


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


async def run_pipeline(websocket: WebSocket):
    """Main entry point: handles one Twilio Media Stream WebSocket connection."""
    await websocket.accept()
    session = CallSession(twilio_ws=websocket)
    tts = CartesiaTTS(session)
    greeting_task: asyncio.Task | None = None

    async def on_utterance(transcript: str):
        """Called by STT when a complete utterance is detected."""
        if not transcript.strip() or not session.is_active:
            return

        asyncio.create_task(publish_event("user_transcript", session.call_sid, text=transcript))
        asyncio.create_task(persist_message(session.call_sid, "user", transcript))

        if session.active_agent_task and not session.active_agent_task.done():
            await handle_interruption(session, tts, source="new_utterance", transcript_hint=transcript)

        turn_id = session.start_new_turn()
        if session.last_utterance_final_at is not None:
            stt_final_to_agent_start_ms = int((time.monotonic() - session.last_utterance_final_at) * 1000)
            logger.info(
                "Turn started call=%s turn=%s stt_final_to_agent_start_ms=%s",
                session.call_sid,
                turn_id,
                stt_final_to_agent_start_ms,
            )

        agent_task = asyncio.create_task(_process_and_speak(session, tts, transcript, turn_id))
        session.set_active_agent_task(agent_task, turn_id)

    async def on_barge_in(transcript_hint: str, source: str):
        """Called by STT when speech should be promoted to hard interruption."""
        if not settings.voice_state_machine_enabled:
            return
        if source == "speech_started":
            logger.info("speech_started_provisional call=%s turn=%s", session.call_sid, session.turn_id)
            return
        if not session.is_speaking and not session.active_agent_task:
            return
        await handle_interruption(session, tts, source=source, transcript_hint=transcript_hint)

    stt = DeepgramSTT(session, on_utterance=on_utterance, on_barge_in=on_barge_in)

    try:
        await stt.connect()
        await tts.connect()

        greeting_task = asyncio.create_task(_send_greeting(session, tts))

        await _receive_loop(websocket, session, stt, tts)

    except WebSocketDisconnect:
        logger.info("Twilio WebSocket disconnected for call %s", session.call_sid)
    except Exception:
        logger.exception("Pipeline error for call %s", session.call_sid)
    finally:
        session.is_active = False
        if greeting_task and not greeting_task.done():
            greeting_task.cancel()
        if session.active_agent_task and not session.active_agent_task.done():
            session.active_agent_task.cancel()
        await stt.close()
        await tts.close()
        if session.call_sid:
            await publish_event("call_ended", session.call_sid)
            await persist_call_ended(session.call_sid)
        logger.info("Pipeline cleaned up for call %s", session.call_sid)


async def _receive_loop(
    websocket: WebSocket,
    session: CallSession,
    stt: DeepgramSTT,
    tts: CartesiaTTS,
):
    """Continuously receive messages from Twilio's WebSocket."""
    nudge_sent = False
    timeout = settings.call_inactivity_timeout_s

    while session.is_active:
        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=timeout)
        except asyncio.TimeoutError:
            if session.is_speaking or (session.active_agent_task and not session.active_agent_task.done()):
                continue
            if not nudge_sent:
                logger.info("Inactivity timeout (%ss) — nudging caller call=%s", timeout, session.call_sid)
                nudge_turn = session.start_new_turn()
                await tts.synthesize_and_stream("Are you still there?", turn_id=nudge_turn)
                session.touch_activity()
                nudge_sent = True
                continue
            logger.info("Second inactivity timeout — ending call %s", session.call_sid)
            goodbye_turn = session.start_new_turn()
            await tts.synthesize_and_stream(
                "It seems like you've stepped away. Feel free to call back anytime. Goodbye!",
                turn_id=goodbye_turn,
            )
            session.is_active = False
            break
        except WebSocketDisconnect:
            break

        nudge_sent = False
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

            asyncio.create_task(publish_event("call_started", session.call_sid, caller_phone=session.caller_phone))
            asyncio.create_task(persist_call_started(session.call_sid, session.caller_phone))

            await _load_tenant_context(session)

            greeting = session.tenant_greeting or DEFAULT_GREETING
            asyncio.create_task(publish_event("agent_transcript", session.call_sid, text=greeting))
            asyncio.create_task(persist_message(session.call_sid, "assistant", greeting))

            session.stream_started.set()

        elif event == "media":
            payload = data["media"]["payload"]
            audio_bytes = twilio_payload_to_deepgram(payload)
            await stt.send_audio(audio_bytes)

        elif event == "mark":
            mark_name = data.get("mark", {}).get("name", "")
            logger.debug("Twilio mark: %s", mark_name)

        elif event == "stop":
            logger.info("Twilio stream stopped for call %s", session.call_sid)
            session.is_active = False
            break


async def _send_greeting(session: CallSession, tts: CartesiaTTS):
    """Send the initial greeting after Twilio start event arrives."""
    try:
        await asyncio.wait_for(session.stream_started.wait(), timeout=3.0)
    except asyncio.TimeoutError:
        logger.warning("Greeting timeout waiting for stream start for call %s", session.call_sid)

    if not session.is_active:
        return

    greeting = session.tenant_greeting or DEFAULT_GREETING
    turn_id = session.start_new_turn()
    completed = await tts.synthesize_and_stream(greeting, turn_id=turn_id)
    if completed and not session.is_stale_turn(turn_id):
        session.messages.append({"role": "assistant", "content": greeting})


async def _process_and_speak(session: CallSession, tts: CartesiaTTS, user_text: str, turn_id: int):
    """Stream the LangGraph agent response directly into TTS as tokens arrive."""
    if session.is_stale_turn(turn_id) or not session.is_active:
        return

    session.messages.append({"role": "user", "content": user_text})
    _trim_history(session)

    full_response_parts: list[str] = []
    tools_called: list[str] = []
    tool_results: list[str] = []
    filler_sent = False
    ctx_started = False
    first_token_at: float | None = None
    interrupted = False

    try:
        async with async_session() as db:
            async for event_type, data in stream_message(
                messages=session.messages,
                caller_phone=session.caller_phone,
                call_sid=session.call_sid,
                tenant_id=session.tenant_id,
                tenant_name=session.tenant_name,
                office_info=session.tenant_office_info,
                emergency_phone=session.tenant_emergency_phone,
                transfer_phone=session.tenant_transfer_phone,
                db=db,
            ):
                if not session.is_active or session.is_stale_turn(turn_id):
                    break

                if event_type == "tool_start" and not filler_sent:
                    tools_called.append(data)
                    pool = FILLER_PHRASES.get(data, FILLER_PHRASES["_default"])
                    filler = random.choice(pool)
                    if ctx_started:
                        logger.info("tool_start_filler_mode=context call=%s turn=%s tool=%s", session.call_sid, turn_id, data)
                        await tts.push_text(f" {filler} ", turn_id=turn_id)
                    else:
                        logger.info("tool_start_filler_mode=oneshot call=%s turn=%s tool=%s", session.call_sid, turn_id, data)
                        completed = await tts.synthesize_and_stream(filler, turn_id=turn_id)
                        if not completed or session.is_stale_turn(turn_id):
                            logger.info(
                                "tool_start_filler_mode=skipped call=%s turn=%s reason=oneshot_incomplete_or_stale",
                                session.call_sid,
                                turn_id,
                            )
                            break
                    filler_sent = True

                elif event_type == "tool_start":
                    tools_called.append(data)

                elif event_type == "tool_result":
                    tool_results.append(data)

                elif event_type == "text":
                    if not data.strip():
                        continue

                    if first_token_at is None and session.turn_started_at is not None:
                        first_token_at = time.monotonic()
                        agent_first_token_ms = int((first_token_at - session.turn_started_at) * 1000)
                        logger.info(
                            "Turn metric call=%s turn=%s agent_first_token_ms=%s",
                            session.call_sid,
                            turn_id,
                            agent_first_token_ms,
                        )

                    full_response_parts.append(data)

                    if not ctx_started:
                        tts.begin_context(turn_id)
                        ctx_started = True

                    await tts.push_text(data, turn_id=turn_id)

        if ctx_started and not session.is_stale_turn(turn_id):
            await tts.finish_context(turn_id=turn_id)

    except asyncio.CancelledError:
        interrupted = True
        logger.debug("_process_and_speak cancelled (barge-in)")
        cancel_reason = "hard_interrupt" if session.is_stale_turn(turn_id) or session.interrupt_in_progress else "manual_cancel"
        await tts.cancel_context(turn_id=turn_id, reason=cancel_reason)
        _save_interrupted_context(session, full_response_parts, tools_called, tool_results)
        raise
    except Exception:
        logger.exception("Agent streaming error")
        await tts.cancel_context(turn_id=turn_id, reason="other")
        if not session.is_stale_turn(turn_id):
            await tts.synthesize_and_stream(
                "I'm sorry, I'm having trouble right now. Let me transfer you to a staff member.",
                turn_id=turn_id,
            )
    finally:
        session.clear_active_agent_task(asyncio.current_task())

    if interrupted or session.is_stale_turn(turn_id):
        return

    response_text = "".join(full_response_parts).strip()
    if response_text:
        session.messages.append({"role": "assistant", "content": response_text})
        asyncio.create_task(publish_event("agent_transcript", session.call_sid, text=response_text))
        asyncio.create_task(persist_message(session.call_sid, "assistant", response_text))
    elif not filler_sent:
        fallback = "I'm sorry, could you repeat that?"
        session.messages.append({"role": "assistant", "content": fallback})
        await tts.synthesize_and_stream(fallback, turn_id=turn_id)

    if session.turn_started_at is not None:
        turn_total_ms = int((time.monotonic() - session.turn_started_at) * 1000)
        logger.info("Turn metric call=%s turn=%s turn_total_ms=%s", session.call_sid, turn_id, turn_total_ms)


def _save_interrupted_context(
    session: CallSession,
    response_parts: list[str],
    tools_called: list[str],
    tool_results: list[str],
) -> None:
    """Preserve context from an interrupted turn so the LLM doesn't lose track."""
    partial_text = "".join(response_parts).strip()
    parts: list[str] = []

    if partial_text:
        parts.append(partial_text)

    if tools_called:
        tool_note = f"[I called {', '.join(tools_called)}"
        if tool_results:
            tool_note += f" and got results: {'; '.join(tool_results)}"
        tool_note += ", but the caller interrupted before I could share the answer.]"
        parts.append(tool_note)
    elif partial_text:
        parts.append("[The caller interrupted me here.]")

    if parts:
        session.messages.append({"role": "assistant", "content": " ".join(parts)})
        logger.info(
            "Saved interrupted context call=%s tools=%s partial_len=%d",
            session.call_sid,
            tools_called,
            len(partial_text),
        )


def _trim_history(session: CallSession) -> None:
    """Keep conversation history within token-budget-friendly bounds."""
    cap = settings.max_conversation_messages
    if cap <= 0 or len(session.messages) <= cap:
        return

    greeting = session.messages[0] if session.messages and session.messages[0]["role"] == "assistant" else None
    tail = session.messages[-cap:]
    if greeting and tail[0] is not greeting:
        session.messages = [greeting] + tail
    else:
        session.messages = tail
