"""Deepgram streaming Speech-to-Text client (SDK v6)."""

import asyncio
import logging
from typing import Callable, Coroutine

from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from deepgram.listen import ListenV1Results, ListenV1SpeechStarted, ListenV1UtteranceEnd

from app.config import settings
from app.voice.session import CallSession

logger = logging.getLogger(__name__)


class DeepgramSTT:
    """Manages a streaming STT connection for one phone call."""

    def __init__(self, session: CallSession, on_utterance: Callable[[str], Coroutine]):
        self.session = session
        self.on_utterance = on_utterance
        self._socket = None
        self._listen_task: asyncio.Task | None = None
        self._final_transcript_parts: list[str] = []
        self._context_manager = None

    async def connect(self):
        client = AsyncDeepgramClient(api_key=settings.deepgram_api_key)

        self._context_manager = client.listen.v1.connect(
            model="nova-2",
            language="en",
            encoding="mulaw",
            sample_rate="8000",
            channels="1",
            punctuate="true",
            smart_format="true",
            interim_results="true",
            utterance_end_ms="1200",
            vad_events="true",
            endpointing="300",
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
            self.session.is_speaking = False
            logger.info("Barge-in detected — user interrupted agent")

    async def _handle_utterance_end(self):
        if self._final_transcript_parts:
            full_utterance = " ".join(self._final_transcript_parts)
            self._final_transcript_parts.clear()
            logger.info("Utterance complete: %s", full_utterance)
            self.session.finalize_utterance(full_utterance)
            if self.on_utterance:
                await self.on_utterance(full_utterance)

    async def _on_error(self, error):
        logger.error("Deepgram error: %s", error)
