"""Cartesia streaming Text-to-Speech client."""

import asyncio
import logging
import uuid

from cartesia import AsyncCartesia

from app.config import settings
from app.voice.audio import cartesia_pcm_to_twilio
from app.voice.session import CallSession

logger = logging.getLogger(__name__)

VOICE_ID = "a0e99841-438c-4a64-b679-ae501e7d6091"  # Cartesia neutral American voice
MODEL_ID = "sonic-2"
OUTPUT_FORMAT = {
    "container": "raw",
    "encoding": "pcm_s16le",
    "sample_rate": 24000,
}


class CartesiaTTS:
    """Manages a streaming TTS WebSocket for one phone call."""

    def __init__(self, session: CallSession):
        self.session = session
        self._client: AsyncCartesia | None = None
        self._ws = None

    async def connect(self):
        self._client = AsyncCartesia(api_key=settings.cartesia_api_key)
        self._ws = await self._client.tts.websocket()
        logger.info("Cartesia TTS connected for call %s", self.session.call_sid)

    async def synthesize_and_stream(self, text: str):
        """Stream TTS audio to the caller. Supports cancellation via barge-in."""
        if not self._ws:
            logger.error("TTS not connected")
            return

        context_id = str(uuid.uuid4())
        self.session.current_tts_context_id = context_id
        self.session.is_speaking = True

        try:
            response = await self._ws.send(
                model_id=MODEL_ID,
                transcript=text,
                voice={"mode": "id", "id": VOICE_ID},
                output_format=OUTPUT_FORMAT,
                context_id=context_id,
            )

            async for chunk in response:
                if not self.session.is_speaking:
                    logger.info("TTS interrupted — stopping stream for context %s", context_id)
                    break

                if chunk.audio:
                    mulaw_b64 = cartesia_pcm_to_twilio(chunk.audio, from_rate=24000)
                    await self.session.send_audio_to_twilio(mulaw_b64)

        except asyncio.CancelledError:
            logger.debug("TTS task cancelled")
        except Exception:
            logger.exception("TTS streaming error")
        finally:
            self.session.is_speaking = False
            self.session.current_tts_context_id = None

    async def close(self):
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                logger.debug("Cartesia WS already closed")
            self._ws = None
        if self._client:
            await self._client.close()
            self._client = None
