"""Barge-in / interruption handling."""

import logging
import time

from app.voice.session import CallSession

logger = logging.getLogger(__name__)


async def handle_interruption(
    session: CallSession,
    tts,
    *,
    source: str = "unknown",
    transcript_hint: str = "",
):
    """Atomically interrupt current assistant output and advance turn ownership."""
    async with session.interruption_lock:
        if not session.is_active:
            return session.turn_id

        if not session.is_speaking and session.active_agent_task is None and session.active_tts_turn_id is None:
            logger.debug("Interruption ignored (nothing active) for call %s", session.call_sid)
            return session.turn_id

        if not session.mark_interrupting():
            logger.debug("Interruption already in progress for call %s", session.call_sid)
            return session.turn_id

        previous_turn = session.turn_id
        interrupted_task = session.active_agent_task

        try:
            # Bump turn id first so stale producers naturally no-op.
            new_turn = session.start_new_turn()
            session.mark_hard_interrupt_promoted()
            session.clear_provisional_speech()

            if interrupted_task and not interrupted_task.done():
                interrupted_task.cancel()
            session.clear_active_agent_task()

            await tts.cancel_context(reason="hard_interrupt")
            clear_started = time.monotonic()
            await session.clear_twilio_audio()
            interrupt_to_clear_ms = int((time.monotonic() - clear_started) * 1000)

            logger.info(
                "Interruption handled call=%s source=%s turn=%s->%s hint=%s interrupt_to_clear_ms=%s",
                session.call_sid,
                source,
                previous_turn,
                new_turn,
                transcript_hint.strip()[:80],
                interrupt_to_clear_ms,
            )
            return new_turn
        finally:
            session.clear_interrupting()
