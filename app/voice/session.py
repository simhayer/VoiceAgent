"""Per-call session state management.

Stripped down for the OpenAI Realtime API architecture — VAD, barge-in,
turn tracking, and muting are all handled server-side by OpenAI.
"""

import logging
import time
from dataclasses import dataclass, field

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class CallSession:
    """Holds state for a single active phone call."""

    # Twilio identifiers
    stream_sid: str = ""
    call_sid: str = ""
    twilio_ws: WebSocket | None = None

    # Caller info
    caller_phone: str = ""

    # Tenant info
    tenant_id: str = ""
    tenant_name: str = ""
    tenant_greeting: str = ""
    tenant_emergency_phone: str | None = None
    tenant_transfer_phone: str | None = None
    tenant_office_info: dict | None = None

    # Lifecycle
    is_active: bool = True

    # Timing
    last_activity_at: float = field(default_factory=time.monotonic)

    def touch_activity(self):
        self.last_activity_at = time.monotonic()

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
        """Tell Twilio to stop playing any queued audio (for interruption)."""
        if not self.twilio_ws or not self.is_active:
            return
        try:
            await self.twilio_ws.send_json({
                "event": "clear",
                "streamSid": self.stream_sid,
            })
        except Exception:
            logger.exception("Failed to clear Twilio audio")
