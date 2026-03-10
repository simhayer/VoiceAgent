"""Voice pipeline orchestrator: wires Twilio ↔ Deepgram STT ↔ LangGraph Agent ↔ Cartesia TTS."""

import asyncio
import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

from app.agent.graph import process_message
from app.database import async_session
from app.voice.audio import twilio_payload_to_deepgram
from app.voice.interruption import handle_interruption
from app.voice.session import CallSession
from app.voice.stt import DeepgramSTT
from app.voice.tts import CartesiaTTS

logger = logging.getLogger(__name__)

GREETING = "Hi, thank you for calling Bright Smile Dental! How can I help you today?"


async def run_pipeline(websocket: WebSocket):
    """Main entry point: handles one Twilio Media Stream WebSocket connection."""
    await websocket.accept()
    session = CallSession(twilio_ws=websocket)
    tts = CartesiaTTS(session)
    pending_agent_task: asyncio.Task | None = None

    async def on_utterance(transcript: str):
        """Called by STT when a complete utterance is detected."""
        nonlocal pending_agent_task

        if pending_agent_task and not pending_agent_task.done():
            pending_agent_task.cancel()
            await handle_interruption(session, tts)

        pending_agent_task = asyncio.create_task(_process_and_speak(session, tts, transcript))

    stt = DeepgramSTT(session, on_utterance=on_utterance)

    try:
        await stt.connect()
        await tts.connect()

        asyncio.create_task(_send_greeting(session, tts))

        await _receive_loop(websocket, session, stt, tts)

    except WebSocketDisconnect:
        logger.info("Twilio WebSocket disconnected for call %s", session.call_sid)
    except Exception:
        logger.exception("Pipeline error for call %s", session.call_sid)
    finally:
        session.is_active = False
        if pending_agent_task and not pending_agent_task.done():
            pending_agent_task.cancel()
        await stt.close()
        await tts.close()
        logger.info("Pipeline cleaned up for call %s", session.call_sid)


async def _receive_loop(
    websocket: WebSocket,
    session: CallSession,
    stt: DeepgramSTT,
    tts: CartesiaTTS,
):
    """Continuously receive messages from Twilio's WebSocket."""
    while session.is_active:
        try:
            raw = await websocket.receive_text()
        except WebSocketDisconnect:
            break

        data = json.loads(raw)
        event = data.get("event")

        if event == "start":
            start_data = data.get("start", {})
            session.stream_sid = start_data.get("streamSid", "")
            session.call_sid = start_data.get("callSid", "")
            custom = start_data.get("customParameters", {})
            session.caller_phone = custom.get("callerPhone", "")
            logger.info(
                "Call started: callSid=%s streamSid=%s",
                session.call_sid,
                session.stream_sid,
            )

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
    """Send the initial greeting after a short delay for connection settling."""
    await asyncio.sleep(0.5)
    session.messages.append({"role": "assistant", "content": GREETING})
    await tts.synthesize_and_stream(GREETING)


async def _process_and_speak(session: CallSession, tts: CartesiaTTS, user_text: str):
    """Run the LangGraph agent on user input and stream the response via TTS."""
    session.messages.append({"role": "user", "content": user_text})

    try:
        async with async_session() as db:
            response_text = await process_message(
                messages=session.messages,
                caller_phone=session.caller_phone,
                db=db,
            )
    except Exception:
        logger.exception("Agent error")
        response_text = "I'm sorry, I'm having trouble processing your request. Let me transfer you to a staff member."

    session.messages.append({"role": "assistant", "content": response_text})
    await tts.synthesize_and_stream(response_text)
