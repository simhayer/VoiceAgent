import uuid

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(50), nullable=False, default="DDS")
    specialties: Mapped[str | None] = mapped_column(Text, nullable=True)

    availability_rules = relationship("AvailabilityRule", back_populates="provider", cascade="all, delete-orphan")
    appointments = relationship("Appointment", back_populates="provider")
