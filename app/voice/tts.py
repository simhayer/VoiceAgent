"""Cartesia streaming Text-to-Speech client.

Supports two modes:
  1. synthesize_and_stream() — one-shot: send full text, stream audio back.
  2. Incremental context — create a context, push() fragments as they arrive
     from the LLM, call done() when finished, and a background task streams
     audio chunks to Twilio concurrently.
"""

import asyncio
import logging
import time

from cartesia import AsyncCartesia

from app.config import settings
from app.voice.audio import encode_twilio_payload
from app.voice.session import CallSession

logger = logging.getLogger(__name__)

MODEL_ID = "sonic-2"
OUTPUT_FORMAT = {
    "container": "raw",
    "encoding": "pcm_mulaw",
    "sample_rate": 8000,
}
VOICE_SPEC = {"mode": "id", "id": settings.cartesia_voice_id}
SPEED = settings.cartesia_speed


class CartesiaTTS:
    """Manages a streaming TTS WebSocket for one phone call."""

    def __init__(self, session: CallSession):
        self.session = session
        self._client: AsyncCartesia | None = None
        self._ws = None
        self._ctx = None
        self._ctx_turn_id: int | None = None
        self._oneshot_turn_id: int | None = None
        self._receive_task: asyncio.Task | None = None
        self._reconnecting: bool = False

    async def connect(self):
        self._client = AsyncCartesia(api_key=settings.cartesia_api_key)
        self._ws = await self._client.tts.websocket()
        logger.info("Cartesia TTS connected for call %s", self.session.call_sid)

    # ------------------------------------------------------------------
    # One-shot mode (greetings, filler phrases, error messages)
    # ------------------------------------------------------------------

    async def synthesize_and_stream(self, text: str, turn_id: int | None = None) -> bool:
        """Send full text and stream all resulting audio to Twilio."""
        if not self._ws:
            logger.error("TTS not connected")
            return False

        target_turn = self.session.turn_id if turn_id is None else turn_id
        if self.session.is_stale_turn(target_turn):
            return False

        context_active_for_turn = self._ctx is not None and self._ctx_turn_id == target_turn
        context_id = self._ctx._context_id if context_active_for_turn else None
        self._oneshot_turn_id = target_turn
        self.session.begin_speaking(target_turn)
        completed = True

        try:
            response = await self._ws.send(
                model_id=MODEL_ID,
                transcript=text,
                voice=VOICE_SPEC,
                output_format=OUTPUT_FORMAT,
                speed=SPEED,
            )

            async for chunk in response:
                if not self.session.should_play_tts_for_turn(target_turn):
                    reason = self._resolve_context_cancel_reason(target_turn)
                    logger.info("TTS interrupted during one-shot stream reason=%s", reason)
                    completed = False
                    break
                if chunk.audio:
                    self._log_tts_first_audio_if_needed(target_turn)
                    mulaw_b64 = encode_twilio_payload(chunk.audio)
                    await self.session.send_audio_to_twilio(mulaw_b64)

        except asyncio.CancelledError:
            logger.debug("TTS one-shot cancelled")
            completed = False
        except Exception:
            logger.exception("TTS one-shot error")
            completed = False
            await self._try_reconnect()
        finally:
            self._oneshot_turn_id = None
            if context_active_for_turn and self._ctx is not None and self._ctx_turn_id == target_turn and not self.session.is_stale_turn(target_turn):
                self.session.begin_speaking(target_turn, context_id=context_id)
            else:
                self.session.stop_speaking(target_turn)

        return completed

    # ------------------------------------------------------------------
    # Incremental context mode (LLM token streaming)
    # ------------------------------------------------------------------

    def begin_context(self, turn_id: int):
        """Open a new Cartesia context and start a background receiver.

        Returns the AsyncWebSocketContext. Use push_text() to send fragments.
        After all fragments are pushed, call finish_context().
        """
        if not self._ws:
            raise RuntimeError("TTS not connected")
        if self.session.is_stale_turn(turn_id):
            raise RuntimeError("Attempted to open TTS context for stale turn")

        self._ctx = self._ws.context()
        self._ctx_turn_id = turn_id
        self.session.begin_speaking(turn_id, context_id=self._ctx._context_id)
        self._receive_task = asyncio.create_task(self._drain_context(self._ctx, turn_id))
        return self._ctx

    async def push_text(self, text: str, turn_id: int):
        """Push a sentence fragment into the active incremental context."""
        if self._ctx is None or self._ctx_turn_id != turn_id:
            logger.debug("No matching active TTS context for push_text turn=%s", turn_id)
            return
        if self.session.is_stale_turn(turn_id):
            return
        await self._ctx.send(
            model_id=MODEL_ID,
            transcript=text,
            voice=VOICE_SPEC,
            output_format=OUTPUT_FORMAT,
            continue_=True,
            speed=SPEED,
        )

    async def _drain_context(self, ctx, turn_id: int):
        """Background task: read audio from the context and forward to Twilio."""
        try:
            async for event in ctx.receive():
                if not self.session.should_play_tts_for_turn(turn_id):
                    reason = self._resolve_context_cancel_reason(turn_id)
                    logger.info("context_cancel_reason=%s turn=%s", reason, turn_id)
                    await ctx.cancel()
                    break
                audio = getattr(event, "audio", None)
                if audio:
                    self._log_tts_first_audio_if_needed(turn_id)
                    mulaw_b64 = encode_twilio_payload(audio)
                    await self.session.send_audio_to_twilio(mulaw_b64)
        except asyncio.CancelledError:
            logger.debug("Context drain cancelled")
        except Exception:
            logger.exception("Context drain error")

    async def finish_context(self, turn_id: int) -> bool:
        """Signal no more input and wait for all audio to be delivered."""
        if self._ctx is None or self._ctx_turn_id != turn_id:
            return False

        completed = not self.session.is_stale_turn(turn_id)
        if self._ctx is not None and completed:
            try:
                await self._ctx.send(
                    model_id=MODEL_ID,
                    transcript="",
                    voice=VOICE_SPEC,
                    output_format=OUTPUT_FORMAT,
                    continue_=False,
                    speed=SPEED,
                )
            except Exception:
                logger.debug("Final context send failed (context may be cancelled)")
                completed = False

        if self._receive_task is not None:
            try:
                await self._receive_task
            except asyncio.CancelledError:
                completed = False

        self._clear_context_refs(turn_id)
        self.session.stop_speaking(turn_id)
        return completed

    async def cancel_context(self, turn_id: int | None = None, reason: str = "manual_cancel"):
        """Cancel the current incremental context immediately (barge-in)."""
        target_turn = self._ctx_turn_id if turn_id is None else turn_id
        if target_turn is None:
            self.session.stop_speaking()
            return

        logger.info("context_cancel_reason=%s turn=%s", reason, target_turn)

        if self._ctx is not None and (turn_id is None or self._ctx_turn_id == turn_id):
            try:
                await self._ctx.cancel()
            except Exception:
                logger.debug("Context cancel failed")

        if self._receive_task is not None and (turn_id is None or self._ctx_turn_id == turn_id):
            self._receive_task.cancel()
            try:
                await self._receive_task
            except (asyncio.CancelledError, Exception):
                pass

        self._clear_context_refs(target_turn)
        if self._oneshot_turn_id == target_turn and reason not in {"hard_interrupt", "stale_turn"}:
            self.session.begin_speaking(target_turn)
        else:
            self.session.stop_speaking(target_turn)

    # ------------------------------------------------------------------

    async def _try_reconnect(self) -> bool:
        """Attempt a single reconnection after a WebSocket failure."""
        if self._reconnecting or not self.session.is_active:
            return False
        self._reconnecting = True
        logger.warning("Attempting Cartesia TTS reconnect for call %s", self.session.call_sid)
        try:
            if self._ws:
                try:
                    await self._ws.close()
                except Exception:
                    pass
                self._ws = None
            if self._client:
                try:
                    await self._client.close()
                except Exception:
                    pass
                self._client = None
            await self.connect()
            logger.info("Cartesia TTS reconnected for call %s", self.session.call_sid)
            return True
        except Exception:
            logger.exception("Cartesia TTS reconnect failed for call %s", self.session.call_sid)
            return False
        finally:
            self._reconnecting = False

    async def close(self):
        await self.cancel_context()
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                logger.debug("Cartesia WS already closed")
            self._ws = None
        if self._client:
            await self._client.close()
            self._client = None

    def _clear_context_refs(self, turn_id: int | None = None):
        if turn_id is not None and self._ctx_turn_id != turn_id:
            return
        self._receive_task = None
        self._ctx = None
        self._ctx_turn_id = None
        self.session.current_tts_context_id = None

    def _log_tts_first_audio_if_needed(self, turn_id: int):
        if self.session.turn_started_at is None:
            return
        if self.session.tts_first_audio_turn_id == turn_id:
            return
        self.session.mark_tts_first_audio(turn_id)
        tts_first_audio_ms = int((time.monotonic() - self.session.turn_started_at) * 1000)
        logger.info(
            "Turn metric call=%s turn=%s tts_first_audio_ms=%s",
            self.session.call_sid,
            turn_id,
            tts_first_audio_ms,
        )

    def _resolve_context_cancel_reason(self, turn_id: int) -> str:
        if self.session.is_stale_turn(turn_id):
            return "stale_turn"
        if self.session.interrupt_in_progress:
            return "hard_interrupt"
        if not self.session.is_speaking:
            return "manual_cancel"
        return "other"
