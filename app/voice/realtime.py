"""OpenAI Realtime API WebSocket client.

Manages a single WebSocket session with the OpenAI Realtime API, handling
session configuration, audio I/O, tool execution, and transcript logging.
"""

import asyncio
import json
import logging
import time
from typing import Awaitable, Callable

import websockets

from app.agent.prompts import get_system_prompt
from app.agent.tools import (
    TOOL_DEFINITIONS,
    TOOL_DISPATCH,
    reset_active_db,
    reset_active_tenant,
    reset_tenant_phones,
    set_active_db,
    set_active_tenant,
    set_tenant_phones,
)
from app.config import settings
from app.database import async_session

logger = logging.getLogger(__name__)

OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime?model={model}"

OnAudioDelta = Callable[[str], Awaitable[None]]
OnSpeechStarted = Callable[[], Awaitable[None]]
OnTranscript = Callable[[str, str], Awaitable[None]]  # (role, text)
OnResponseDone = Callable[[], Awaitable[None]]
OnTokenDelta = Callable[[str], Awaitable[None]]  # (partial text)
OnToolCall = Callable[[str, str, str, str], Awaitable[None]]  # (tool_call_id, tool_name, status, result)


class RealtimeSession:
    """Wraps the OpenAI Realtime WebSocket for one phone call."""

    def __init__(
        self,
        *,
        tenant_id: str,
        tenant_name: str,
        office_info: dict | None,
        emergency_phone: str | None,
        transfer_phone: str | None,
        on_audio_delta: OnAudioDelta,
        on_speech_started: OnSpeechStarted,
        on_transcript: OnTranscript,
        on_response_done: OnResponseDone,
        on_token_delta: OnTokenDelta | None = None,
        on_tool_call: OnToolCall | None = None,
    ):
        self.tenant_id = tenant_id
        self.tenant_name = tenant_name
        self.office_info = office_info
        self.emergency_phone = emergency_phone
        self.transfer_phone = transfer_phone

        self._on_audio_delta = on_audio_delta
        self._on_speech_started = on_speech_started
        self._on_transcript = on_transcript
        self._on_response_done = on_response_done
        self._on_token_delta = on_token_delta
        self._on_tool_call = on_tool_call

        self._ws: websockets.WebSocketClientProtocol | None = None
        self._receive_task: asyncio.Task | None = None
        self._is_open = False
        self._session_configured = asyncio.Event()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self):
        url = OPENAI_REALTIME_URL.format(model=settings.openai_realtime_model)
        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "OpenAI-Beta": "realtime=v1",
        }
        self._ws = await websockets.connect(url, additional_headers=headers, max_size=None)
        self._is_open = True
        self._receive_task = asyncio.create_task(self._receive_loop())
        logger.info("OpenAI Realtime WS connected model=%s", settings.openai_realtime_model)

    async def configure_session(self):
        instructions = get_system_prompt(
            tenant_name=self.tenant_name,
            office_info=self.office_info,
        )
        session_update = {
            "type": "session.update",
            "session": {
                "instructions": instructions,
                "voice": settings.openai_realtime_voice,
                "input_audio_format": "g711_ulaw",
                "output_audio_format": "g711_ulaw",
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500,
                },
                "input_audio_transcription": {
                    "model": "whisper-1",
                },
                "tools": TOOL_DEFINITIONS,
                "tool_choice": "auto",
            },
        }
        await self._send(session_update)
        logger.info("Session update sent, awaiting confirmation")
        await asyncio.wait_for(self._session_configured.wait(), timeout=10.0)

    async def close(self):
        self._is_open = False
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
        logger.info("OpenAI Realtime WS closed")

    # ------------------------------------------------------------------
    # Sending events
    # ------------------------------------------------------------------

    async def _send(self, event: dict):
        if self._ws and self._is_open:
            await self._ws.send(json.dumps(event))

    async def send_audio(self, base64_audio: str):
        """Forward Twilio mulaw audio to OpenAI (zero conversion)."""
        await self._send({
            "type": "input_audio_buffer.append",
            "audio": base64_audio,
        })

    async def send_greeting(self, greeting_text: str):
        """Inject the greeting as an assistant message and have the model speak it."""
        await self._send({
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": greeting_text}],
            },
        })
        await self._send({"type": "response.create"})

    async def send_text_message(self, text: str):
        """Inject an assistant text message and trigger a spoken response."""
        await self._send({
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": text}],
            },
        })
        await self._send({"type": "response.create"})

    # ------------------------------------------------------------------
    # Receive loop
    # ------------------------------------------------------------------

    async def _receive_loop(self):
        try:
            async for raw in self._ws:
                if not self._is_open:
                    break
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("Non-JSON message from OpenAI Realtime")
                    continue
                await self._dispatch(event)
        except websockets.ConnectionClosedError as e:
            logger.warning("OpenAI Realtime WS closed unexpectedly: %s", e)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("OpenAI Realtime receive loop error")
        finally:
            self._is_open = False

    async def _dispatch(self, event: dict):
        etype = event.get("type", "")

        if etype == "session.created":
            logger.info("Session created session_id=%s", event.get("session", {}).get("id"))

        elif etype == "session.updated":
            logger.info("Session configured successfully")
            self._session_configured.set()

        elif etype == "response.audio.delta":
            delta = event.get("delta", "")
            if delta:
                await self._on_audio_delta(delta)

        elif etype == "input_audio_buffer.speech_started":
            logger.debug("VAD speech started")
            await self._on_speech_started()

        elif etype == "response.audio_transcript.delta":
            # Word-by-word streaming delta for assistant speech
            delta = event.get("delta", "")
            if delta and self._on_token_delta:
                await self._on_token_delta(delta)

        elif etype == "response.audio_transcript.done":
            text = event.get("transcript", "")
            if text:
                await self._on_transcript("assistant", text)

        elif etype == "conversation.item.input_audio_transcription.completed":
            text = event.get("transcript", "")
            if text:
                await self._on_transcript("user", text)

        elif etype == "response.function_call_arguments.done":
            await self._handle_function_call(event)

        elif etype == "response.done":
            await self._on_response_done()
            response = event.get("response", {})
            usage = response.get("usage", {})
            if usage:
                logger.info(
                    "Response done usage=%s status=%s",
                    json.dumps(usage),
                    response.get("status"),
                )

        elif etype == "error":
            err = event.get("error", {})
            logger.error("OpenAI Realtime error: %s", json.dumps(err))

        elif etype in (
            "response.created",
            "response.output_item.added",
            "response.output_item.done",
            "response.content_part.added",
            "response.content_part.done",
            "response.audio.done",
            "response.text.delta",
            "response.text.done",
            "conversation.item.created",
            "input_audio_buffer.committed",
            "input_audio_buffer.speech_stopped",
            "input_audio_buffer.cleared",
            "response.function_call_arguments.delta",
            "rate_limits.updated",
        ):
            pass  # known but unneeded
        else:
            logger.debug("Unhandled realtime event: %s", etype)

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    async def _handle_function_call(self, event: dict):
        fn_name = event.get("name", "")
        call_id = event.get("call_id", "")
        raw_args = event.get("arguments", "{}")
        t0 = time.monotonic()

        logger.info("Tool call received name=%s call_id=%s", fn_name, call_id)

        # Notify dashboard of tool_start
        if self._on_tool_call:
            try:
                args = json.loads(raw_args) if raw_args else {}
            except json.JSONDecodeError:
                args = {}
            await self._on_tool_call(call_id, fn_name, "start", json.dumps(args))

        handler = TOOL_DISPATCH.get(fn_name)
        if not handler:
            result = json.dumps({"error": f"Unknown tool: {fn_name}"})
        else:
            try:
                args = json.loads(raw_args) if raw_args else {}
                async with async_session() as db:
                    db_tok = set_active_db(db)
                    tenant_tok = set_active_tenant(self.tenant_id)
                    phone_toks = set_tenant_phones(self.emergency_phone, self.transfer_phone)
                    try:
                        result = await handler(**args)
                    finally:
                        reset_active_db(db_tok)
                        reset_active_tenant(tenant_tok)
                        reset_tenant_phones(phone_toks)
            except Exception:
                logger.exception("Tool execution failed name=%s", fn_name)
                result = json.dumps({"error": f"Tool {fn_name} failed"})

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info("Tool call completed name=%s elapsed_ms=%d", fn_name, elapsed_ms)

        # Notify dashboard of tool_end
        if self._on_tool_call:
            await self._on_tool_call(call_id, fn_name, "end", result)

        await self._send({
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": result,
            },
        })
        await self._send({"type": "response.create"})
