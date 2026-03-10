"""Per-call session state management."""

import asyncio
import logging
from dataclasses import dataclass, field

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class CallSession:
    """Holds all state for a single active phone call."""

    # Twilio identifiers
    stream_sid: str = ""
    call_sid: str = ""

    # The FastAPI WebSocket connected to Twilio
    twilio_ws: WebSocket | None = None

    # Conversation history for the LLM (list of message dicts)
    messages: list[dict] = field(default_factory=list)

    # Voice pipeline state
    is_speaking: bool = False
    current_tts_context_id: str | None = None
    transcript_buffer: str = ""

    # Caller info (populated from Twilio start event)
    caller_phone: str = ""

    # Lifecycle
    is_active: bool = True

    # Async events for coordination
    utterance_ready: asyncio.Event = field(default_factory=asyncio.Event)

    def reset_utterance(self):
        self.transcript_buffer = ""
        self.utterance_ready.clear()

    def finalize_utterance(self, transcript: str):
        self.transcript_buffer = transcript.strip()
        if self.transcript_buffer:
            self.utterance_ready.set()

    async def send_audio_to_twilio(self, mulaw_base64: str):
        """Send an audio chunk back to the caller via Twilio's WebSocket."""
        if not self.twilio_ws or not self.is_active:
            return
        try:
            await self.twilio_ws.send_json({
                "event": "media",
                "streamSid": self.stream_sid,
                "media": {"payload": mulaw_base64},
            })
        except Exception:
            logger.exception("Failed to send audio to Twilio")

    async def clear_twilio_audio(self):
        """Tell Twilio to stop playing any queued audio (for barge-in)."""
        if not self.twilio_ws or not self.is_active:
            return
        try:
            await self.twilio_ws.send_json({
                "event": "clear",
                "streamSid": self.stream_sid,
            })
        except Exception:
            logger.exception("Failed to clear Twilio audio")

    async def send_mark(self, name: str):
        """Send a mark event to Twilio to track playback position."""
        if not self.twilio_ws or not self.is_active:
            return
        try:
            await self.twilio_ws.send_json({
                "event": "mark",
                "streamSid": self.stream_sid,
                "mark": {"name": name},
            })
        except Exception:
            logger.exception("Failed to send mark to Twilio")
