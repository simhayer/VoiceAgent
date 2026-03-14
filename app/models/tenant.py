import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    twilio_phone_number: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)

    cartesia_voice_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    greeting_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_prompt_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    emergency_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    transfer_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), default="America/Los_Angeles")

    plan: Mapped[str] = mapped_column(String(20), default="starter")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    providers = relationship("Provider", back_populates="tenant")
    patients = relationship("Patient", back_populates="tenant")
    appointments = relationship("Appointment", back_populates="tenant")
    office_configs = relationship("OfficeConfig", back_populates="tenant")
    users = relationship("User", back_populates="tenant")
    agent_settings = relationship(
        "TenantAgentSettings",
        back_populates="tenant",
        uselist=False,
        cascade="all, delete-orphan",
    )
