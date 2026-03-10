"""Barge-in / interruption handling.

When the patient speaks while the agent is talking:
1. Deepgram fires SpeechStarted → session.is_speaking set to False (in stt.py)
2. TTS streaming loop sees is_speaking=False and stops (in tts.py)
3. This module coordinates cleanup: clear Twilio audio queue.
"""

import logging

from app.voice.session import CallSession

logger = logging.getLogger(__name__)


async def handle_interruption(session: CallSession, tts):
    """Called when barge-in is detected. Stops all outbound audio."""
    logger.info("Handling interruption for call %s", session.call_sid)
    session.is_speaking = False
    session.current_tts_context_id = None
    await session.clear_twilio_audio()
