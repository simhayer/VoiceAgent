"""Tenant resolution: maps inbound signals (phone number, ID) to a Tenant."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.tenant import Tenant
from app.models.tenant_agent_settings import TenantAgentSettings


async def resolve_tenant_by_phone(db: AsyncSession, called_number: str) -> Tenant | None:
    """Look up the tenant that owns a given Twilio phone number."""
    result = await db.execute(
        select(Tenant).where(
            Tenant.twilio_phone_number == called_number,
            Tenant.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def get_tenant_by_id(db: AsyncSession, tenant_id: str) -> Tenant | None:
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    return result.scalar_one_or_none()


async def get_tenant_with_agent_settings(db: AsyncSession, tenant_id: str) -> Tenant | None:
    """Load tenant and its agent_settings in one query."""
    result = await db.execute(
        select(Tenant)
        .where(Tenant.id == tenant_id)
        .options(selectinload(Tenant.agent_settings))
    )
    return result.scalar_one_or_none()
