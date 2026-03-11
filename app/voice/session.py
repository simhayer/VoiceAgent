"""Per-call session state management."""

import asyncio
import logging
import time
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
    active_tts_turn_id: int | None = None

    # Caller info (populated from Twilio start event)
    caller_phone: str = ""

    # Lifecycle
    is_active: bool = True

    # Async events for coordination
    utterance_ready: asyncio.Event = field(default_factory=asyncio.Event)
    stream_started: asyncio.Event = field(default_factory=asyncio.Event)

    # Turn state machine
    turn_id: int = 0
    active_agent_task: asyncio.Task | None = None
    active_agent_turn_id: int | None = None
    interruption_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    interrupt_in_progress: bool = False

    # Timing / observability
    last_activity_at: float = field(default_factory=time.monotonic)
    turn_started_at: float | None = None
    interrupt_at: float | None = None
    last_utterance_final_at: float | None = None
    tts_first_audio_turn_id: int | None = None
    provisional_speech_at: float | None = None
    provisional_speech_turn_id: int | None = None
    hard_interrupt_promoted_at: float | None = None

    def touch_activity(self):
        self.last_activity_at = time.monotonic()

    def reset_utterance(self):
        self.transcript_buffer = ""
        self.utterance_ready.clear()

    def finalize_utterance(self, transcript: str):
        self.transcript_buffer = transcript.strip()
        if self.transcript_buffer:
            self.last_utterance_final_at = time.monotonic()
            self.touch_activity()
            self.utterance_ready.set()

    def start_new_turn(self) -> int:
        """Advance turn ownership and reset per-turn timing state."""
        self.turn_id += 1
        self.turn_started_at = time.monotonic()
        self.tts_first_audio_turn_id = None
        self.interrupt_at = None
        self.clear_provisional_speech()
        return self.turn_id

    def is_stale_turn(self, turn_id: int) -> bool:
        return turn_id != self.turn_id

    def set_active_agent_task(self, task: asyncio.Task, turn_id: int):
        self.active_agent_task = task
        self.active_agent_turn_id = turn_id

    def clear_active_agent_task(self, task: asyncio.Task | None = None):
        if task is not None and self.active_agent_task is not task:
            return
        self.active_agent_task = None
        self.active_agent_turn_id = None

    def begin_speaking(self, turn_id: int, context_id: str | None = None):
        self.is_speaking = True
        self.active_tts_turn_id = turn_id
        self.current_tts_context_id = context_id

    def stop_speaking(self, turn_id: int | None = None):
        if turn_id is not None and self.active_tts_turn_id != turn_id:
            return
        self.is_speaking = False
        self.active_tts_turn_id = None
        self.current_tts_context_id = None

    def should_play_tts_for_turn(self, turn_id: int) -> bool:
        return self.is_speaking and self.active_tts_turn_id == turn_id and not self.is_stale_turn(turn_id)

    def mark_interrupting(self) -> bool:
        if self.interrupt_in_progress:
            return False
        self.interrupt_in_progress = True
        self.interrupt_at = time.monotonic()
        return True

    def clear_interrupting(self):
        self.interrupt_in_progress = False

    def mark_tts_first_audio(self, turn_id: int):
        if self.tts_first_audio_turn_id is None:
            self.tts_first_audio_turn_id = turn_id

    def mark_provisional_speech(self):
        self.provisional_speech_at = time.monotonic()
        self.provisional_speech_turn_id = self.turn_id

    def clear_provisional_speech(self):
        self.provisional_speech_at = None
        self.provisional_speech_turn_id = None

    def mark_hard_interrupt_promoted(self):
        self.hard_interrupt_promoted_at = time.monotonic()

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
