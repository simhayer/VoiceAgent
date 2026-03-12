"""Deepgram streaming Speech-to-Text client (SDK v6)."""

import asyncio
import logging
import time
from typing import Awaitable, Callable

from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from deepgram.listen import ListenV1Results, ListenV1SpeechStarted, ListenV1UtteranceEnd

from app.config import settings
from app.voice.session import CallSession

logger = logging.getLogger(__name__)


class DeepgramSTT:
    """Manages a streaming STT connection for one phone call."""

    def __init__(
        self,
        session: CallSession,
        on_utterance: Callable[[str], Awaitable[None]],
        on_barge_in: Callable[[str, str], Awaitable[None]] | None = None,
    ):
        self.session = session
        self.on_utterance = on_utterance
        self.on_barge_in = on_barge_in
        self._socket = None
        self._listen_task: asyncio.Task | None = None
        self._final_transcript_parts: list[str] = []
        self._context_manager = None
        self._barge_in_active: bool = False
        self._barge_in_dispatched: bool = False
        self._reconnecting: bool = False

    async def connect(self):
        client = AsyncDeepgramClient(api_key=settings.deepgram_api_key)
        utterance_end_ms = max(1000, int(settings.deepgram_utterance_end_ms))
        endpointing_ms = max(10, int(settings.deepgram_endpointing_ms))

        if utterance_end_ms != settings.deepgram_utterance_end_ms:
            logger.warning(
                "Adjusted deepgram_utterance_end_ms from %s to %s (minimum supported)",
                settings.deepgram_utterance_end_ms,
                utterance_end_ms,
            )

        self._context_manager = client.listen.v1.connect(
            model="nova-2",
            language="en",
            encoding="mulaw",
            sample_rate="8000",
            channels="1",
            punctuate="true",
            smart_format="true",
            interim_results="true",
            utterance_end_ms=str(utterance_end_ms),
            vad_events="true",
            endpointing=str(endpointing_ms),
        )
        self._socket = await self._context_manager.__aenter__()

        self._socket.on(EventType.MESSAGE, self._on_message)
        self._socket.on(EventType.ERROR, self._on_error)

        self._listen_task = asyncio.create_task(self._socket.start_listening())
        logger.info("Deepgram STT connected for call %s", self.session.call_sid)

    async def send_audio(self, audio_bytes: bytes):
        if self._socket:
            await self._socket.send_media(audio_bytes)

    async def close(self):
        if self._socket:
            try:
                await self._socket.send_close_stream()
            except Exception:
                logger.debug("Deepgram close_stream failed (already closed)")
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
        if self._context_manager:
            try:
                await self._context_manager.__aexit__(None, None, None)
            except Exception:
                pass
        self._socket = None

    async def _on_message(self, message):
        if isinstance(message, ListenV1Results):
            await self._handle_transcript(message)
        elif isinstance(message, ListenV1SpeechStarted):
            await self._handle_speech_started()
        elif isinstance(message, ListenV1UtteranceEnd):
            await self._handle_utterance_end()

    async def _handle_transcript(self, result: ListenV1Results):
        try:
            alt = result.channel.alternatives[0]
            transcript = alt.transcript
            if not transcript:
                return

            if self.session.is_speaking and self._should_trigger_barge_in(
                transcript=transcript,
                is_final=bool(result.is_final),
                confidence=getattr(alt, "confidence", None),
            ):
                self._barge_in_active = True
                source = "final" if bool(result.is_final) else "interim"
                await self._promote_barge_in_to_hard(transcript, source=source)

            if result.is_final:
                self._final_transcript_parts.append(transcript)
                logger.debug("Deepgram final: %s", transcript)
            else:
                logger.debug("Deepgram interim: %s", transcript)
        except (IndexError, AttributeError):
            pass

    async def _handle_speech_started(self):
        logger.debug("Deepgram speech started")
        if self.session.is_speaking:
            self._barge_in_active = True
            self.session.mark_provisional_speech()
            logger.info(
                "speech_started_provisional call=%s turn=%s",
                self.session.call_sid,
                self.session.turn_id,
            )

    async def _handle_utterance_end(self):
        if self._final_transcript_parts:
            full_utterance = " ".join(self._final_transcript_parts).strip()
            self._final_transcript_parts.clear()

            # If they just said "wait" to pause the agent, swallow it
            word_count = len(full_utterance.split())
            if self._barge_in_active and word_count <= 3 and any(w in full_utterance.lower() for w in ["wait", "stop", "hold"]):
                logger.info("Swallowed short interrupt: %s", full_utterance)
                self._barge_in_active = False
                self._barge_in_dispatched = False
                self.session.clear_provisional_speech()
                return

            self._barge_in_active = False
            self._barge_in_dispatched = False
            self.session.clear_provisional_speech()
            logger.info("Utterance complete: %s", full_utterance)
            self.session.finalize_utterance(full_utterance)
            if self.on_utterance:
                await self.on_utterance(full_utterance)
        else:
            self._barge_in_active = False
            self._barge_in_dispatched = False
            self.session.clear_provisional_speech()

    async def _on_error(self, error):
        logger.error("Deepgram error: %s", error)
        if not self._reconnecting and self.session.is_active:
            await self._try_reconnect()

    async def _try_reconnect(self):
        """Attempt a single reconnection after a WebSocket failure."""
        if self._reconnecting:
            return
        self._reconnecting = True
        logger.warning("Attempting Deepgram STT reconnect for call %s", self.session.call_sid)
        try:
            await self.close()
            await self.connect()
            logger.info("Deepgram STT reconnected for call %s", self.session.call_sid)
        except Exception:
            logger.exception("Deepgram STT reconnect failed for call %s", self.session.call_sid)
        finally:
            self._reconnecting = False

    def _should_trigger_barge_in(
        self,
        *,
        transcript: str,
        is_final: bool,
        confidence: float | None,
    ) -> bool:
        text = transcript.strip().lower()
        if not text:
            return False

        backchannels = {
            "uh",
            "um",
            "hmm",
            "mm",
            "mhm",
            "uh huh",
            "uh-huh",
            "yeah",
            "right",
            "ok",
            "okay",
        }
        if text in backchannels:
            return False

        word_count = len(text.split())
        if len(text) < settings.stt_barge_in_min_chars and word_count < settings.stt_barge_in_min_words:
            return False

        if not is_final and confidence is not None and confidence < settings.stt_barge_in_min_confidence:
            return False

        return True

    async def _promote_barge_in_to_hard(self, transcript_hint: str, source: str):
        if self._barge_in_dispatched:
            return

        debounce_seconds = max(0, settings.stt_barge_in_promotion_debounce_ms) / 1000
        now = time.monotonic()
        if self.session.hard_interrupt_promoted_at is not None:
            elapsed = now - self.session.hard_interrupt_promoted_at
            if elapsed < debounce_seconds:
                logger.info(
                    "barge_in_promoted_to_hard skipped_debounce call=%s source=%s elapsed_ms=%s",
                    self.session.call_sid,
                    source,
                    int(elapsed * 1000),
                )
                return

        self._barge_in_dispatched = True
        self.session.mark_hard_interrupt_promoted()

        logger.info(
            "barge_in_promoted_to_hard call=%s source=%s transcript=%s",
            self.session.call_sid,
            source,
            transcript_hint[:80],
        )

        if self.on_barge_in:
            await self.on_barge_in(transcript_hint, source)
            return

        # Safety fallback if no callback is provided.
        self.session.stop_speaking()
        await self.session.clear_twilio_audio()
