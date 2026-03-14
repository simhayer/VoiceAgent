"""Per-call session state management.

Stripped down for the OpenAI Realtime API architecture — VAD, barge-in,
turn tracking, and muting are all handled server-side by OpenAI.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fastapi import WebSocket

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.services.tenant_runtime import TenantRuntimeConfig


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
    # Per-tenant agent settings (from tenant_agent_settings)
    tenant_openai_model: str | None = None
    tenant_openai_voice: str | None = None
    tenant_system_prompt_override: str | None = None

    # Lifecycle
    is_active: bool = True

    # Timing
    last_activity_at: float = field(default_factory=time.monotonic)

    def touch_activity(self):
        self.last_activity_at = time.monotonic()

    def apply_runtime_config(self, config: "TenantRuntimeConfig") -> None:
        self.tenant_name = config.name
        self.tenant_greeting = config.greeting_message or ""
        self.tenant_emergency_phone = config.emergency_phone
        self.tenant_transfer_phone = config.transfer_phone
        self.tenant_office_info = dict(config.office_info)
        self.tenant_openai_model = config.openai_realtime_model
        self.tenant_openai_voice = config.openai_realtime_voice
        self.tenant_system_prompt_override = config.system_prompt_override

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
