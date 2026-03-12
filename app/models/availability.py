import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AvailabilityRule(Base):
    """Recurring weekly schedule block for a provider.

    day_of_week: 0=Monday ... 6=Sunday (ISO weekday)
    """

    __tablename__ = "availability_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[str] = mapped_column(String(5), nullable=False)
    end_time: Mapped[str] = mapped_column(String(5), nullable=False)

    provider = relationship("Provider", back_populates="availability_rules")
