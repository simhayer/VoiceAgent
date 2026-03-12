import uuid

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class OfficeConfig(Base):
    """Key-value store for office information, FAQ, and policies."""

    __tablename__ = "office_config"
    __table_args__ = (
        UniqueConstraint("tenant_id", "key", name="uq_office_config_tenant_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="general")

    tenant = relationship("Tenant", back_populates="office_configs")
