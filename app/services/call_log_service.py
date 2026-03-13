"""Service for persisting call logs and messages to the database."""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import async_session
from app.models.call_log import CallLog, CallMessage

logger = logging.getLogger(__name__)


async def persist_call_started(call_sid: str, caller_phone: str, tenant_id: str) -> None:
    """Create a new CallLog row when a call begins."""
    try:
        async with async_session() as db:
            existing = await db.execute(
                select(CallLog).where(CallLog.call_sid == call_sid)
            )
            if existing.scalars().first():
                return  # already recorded (idempotent)
            log = CallLog(
                call_sid=call_sid,
                tenant_id=tenant_id,
                caller_phone=caller_phone or "Unknown",
                status="active",
                started_at=datetime.now(timezone.utc),
            )
            db.add(log)
            await db.commit()
    except Exception:
        logger.exception("Failed to persist call_started for %s", call_sid)


async def persist_call_ended(call_sid: str) -> None:
    """Mark an existing CallLog as ended."""
    try:
        async with async_session() as db:
            result = await db.execute(
                select(CallLog).where(CallLog.call_sid == call_sid)
            )
            log = result.scalars().first()
            if log:
                log.status = "ended"
                log.ended_at = datetime.now(timezone.utc)
                await db.commit()
    except Exception:
        logger.exception("Failed to persist call_ended for %s", call_sid)


async def persist_message(
    call_sid: str,
    role: str,
    content: str,
    tool_name: str | None = None,
    tool_args: dict | None = None,
) -> None:
    """Append a transcript / tool message to an existing CallLog."""
    try:
        async with async_session() as db:
            result = await db.execute(
                select(CallLog).where(CallLog.call_sid == call_sid)
            )
            log = result.scalars().first()
            if not log:
                logger.warning("persist_message: no CallLog for %s", call_sid)
                return

            # Determine next sequence number
            msg_result = await db.execute(
                select(CallMessage)
                .where(CallMessage.call_log_id == log.id)
                .order_by(CallMessage.sequence.desc())
                .limit(1)
            )
            last = msg_result.scalars().first()
            seq = (last.sequence + 1) if last else 0

            msg = CallMessage(
                call_log_id=log.id,
                role=role,
                content=content,
                tool_name=tool_name,
                tool_args=json.dumps(tool_args) if tool_args else None,
                sequence=seq,
                timestamp=datetime.now(timezone.utc),
            )
            db.add(msg)
            await db.commit()
    except Exception:
        logger.exception("Failed to persist message for %s", call_sid)
