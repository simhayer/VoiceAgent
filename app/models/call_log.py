"""Persisted call logs and transcript messages."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CallLog(Base):
    __tablename__ = "call_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    call_sid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    caller_phone: Mapped[str] = mapped_column(String(20), nullable=False, default="Unknown")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Token usage (populated when call ends)
    llm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    voice_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    messages: Mapped[list["CallMessage"]] = relationship(
        "CallMessage", back_populates="call_log", order_by="CallMessage.sequence",
        cascade="all, delete-orphan",
    )


class CallMessage(Base):
    __tablename__ = "call_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    call_log_id: Mapped[str] = mapped_column(ForeignKey("call_logs.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)          # user | assistant | tool_start | tool_end
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tool_args: Mapped[str | None] = mapped_column(Text, nullable=True)     # JSON-encoded
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)         # ordering
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    call_log: Mapped["CallLog"] = relationship("CallLog", back_populates="messages")
