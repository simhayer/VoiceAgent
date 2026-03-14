"""Per-tenant agent settings: prompt, LLM model, voice (stored in Supabase)."""

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TenantAgentSettings(Base):
    """One row per tenant: OpenAI model, voice, and optional system prompt override."""

    __tablename__ = "tenant_agent_settings"

    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    openai_realtime_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    openai_realtime_voice: Mapped[str | None] = mapped_column(String(60), nullable=True)
    system_prompt_override: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenant = relationship("Tenant", back_populates="agent_settings")
