"""In-memory cache for rarely-changing reference data (providers, availability rules).

Eliminates 2 of 3 DB round-trips from the hot path (check_availability).
Call ``warm()`` once at startup; use ``refresh()`` if admin data changes.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.availability import AvailabilityRule
from app.models.provider import Provider

logger = logging.getLogger(__name__)

_providers: list[Provider] = []
_rules: list[AvailabilityRule] = []


async def warm(db: AsyncSession) -> None:
    """Fetch providers and availability rules into memory."""
    global _providers, _rules

    prov_result = await db.execute(select(Provider))
    _providers = list(prov_result.scalars().all())

    rules_result = await db.execute(select(AvailabilityRule))
    _rules = list(rules_result.scalars().all())

    logger.info("Cache warmed: %d providers, %d availability rules", len(_providers), len(_rules))


async def refresh(db: AsyncSession) -> None:
    """Re-fetch cached data (alias kept for readability at call-sites)."""
    await warm(db)


def get_providers(provider_id: str | None = None) -> list[Provider]:
    if provider_id:
        return [p for p in _providers if p.id == provider_id]
    return list(_providers)


def get_rules(provider_ids: list[str] | None = None) -> list[AvailabilityRule]:
    if provider_ids:
        id_set = set(provider_ids)
        return [r for r in _rules if r.provider_id in id_set]
    return list(_rules)
