"""In-memory cache for rarely-changing reference data (providers, availability rules).

Tenant-scoped: each tenant's data is stored in a separate dict entry.
Call ``warm_all()`` at startup; use ``warm_tenant()`` or ``refresh()`` when admin data changes.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.availability import AvailabilityRule
from app.models.provider import Provider
from app.models.tenant import Tenant
from app.models.office import OfficeConfig

logger = logging.getLogger(__name__)

_providers: dict[str, list[Provider]] = {}
_rules: dict[str, list[AvailabilityRule]] = {}
_office_configs: dict[str, list[OfficeConfig]] = {}


async def warm_tenant(db: AsyncSession, tenant_id: str) -> None:
    """Fetch providers, availability rules, and office configs for a single tenant into memory."""
    prov_result = await db.execute(select(Provider).where(Provider.tenant_id == tenant_id))
    _providers[tenant_id] = list(prov_result.scalars().all())

    rules_result = await db.execute(select(AvailabilityRule).where(AvailabilityRule.tenant_id == tenant_id))
    _rules[tenant_id] = list(rules_result.scalars().all())

    office_result = await db.execute(select(OfficeConfig).where(OfficeConfig.tenant_id == tenant_id))
    _office_configs[tenant_id] = list(office_result.scalars().all())

    logger.info(
        "Cache warmed for tenant %s: %d providers, %d availability rules, %d office configs",
        tenant_id, len(_providers[tenant_id]), len(_rules[tenant_id]), len(_office_configs[tenant_id]),
    )


async def warm_all(db: AsyncSession) -> None:
    """Load cache data for every active tenant."""
    result = await db.execute(select(Tenant.id).where(Tenant.is_active.is_(True)))
    tenant_ids = list(result.scalars().all())
    for tid in tenant_ids:
        await warm_tenant(db, tid)
    logger.info("Cache warmed for %d tenants", len(tenant_ids))


async def refresh(db: AsyncSession, tenant_id: str) -> None:
    """Re-fetch cached data for a tenant."""
    await warm_tenant(db, tenant_id)


def get_providers(tenant_id: str, provider_id: str | None = None) -> list[Provider]:
    providers = _providers.get(tenant_id, [])
    if provider_id:
        return [p for p in providers if p.id == provider_id]
    return list(providers)


def get_rules(tenant_id: str, provider_ids: list[str] | None = None) -> list[AvailabilityRule]:
    rules = _rules.get(tenant_id, [])
    if provider_ids:
        id_set = set(provider_ids)
        return [r for r in rules if r.provider_id in id_set]
    return list(rules)


def get_office_configs(tenant_id: str) -> list[OfficeConfig]:
    return list(_office_configs.get(tenant_id, []))
