"""Tenant runtime configuration cache backed by Supabase/Postgres data."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.office import OfficeConfig
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class TenantRuntimeConfig:
    tenant_id: str
    name: str
    slug: str
    twilio_phone_number: str | None
    greeting_message: str | None
    emergency_phone: str | None
    transfer_phone: str | None
    system_prompt_override: str | None
    openai_realtime_model: str | None
    openai_realtime_voice: str | None
    office_info: dict[str, str]


_configs_by_tenant_id: dict[str, TenantRuntimeConfig] = {}
_tenant_id_by_phone: dict[str, str] = {}
_fingerprints_by_tenant_id: dict[str, str] = {}


def _fingerprint(config: TenantRuntimeConfig) -> str:
    payload = {
        "tenant_id": config.tenant_id,
        "name": config.name,
        "slug": config.slug,
        "twilio_phone_number": config.twilio_phone_number,
        "greeting_message": config.greeting_message,
        "emergency_phone": config.emergency_phone,
        "transfer_phone": config.transfer_phone,
        "system_prompt_override": config.system_prompt_override,
        "openai_realtime_model": config.openai_realtime_model,
        "openai_realtime_voice": config.openai_realtime_voice,
        "office_info": config.office_info,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _to_runtime_config(tenant: Tenant, office_info: dict[str, str]) -> TenantRuntimeConfig:
    agent_settings = tenant.agent_settings
    return TenantRuntimeConfig(
        tenant_id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        twilio_phone_number=tenant.twilio_phone_number,
        greeting_message=tenant.greeting_message,
        emergency_phone=tenant.emergency_phone,
        transfer_phone=tenant.transfer_phone,
        system_prompt_override=(
            agent_settings.system_prompt_override
            if agent_settings and agent_settings.system_prompt_override
            else tenant.system_prompt_override
        ),
        openai_realtime_model=(
            agent_settings.openai_realtime_model if agent_settings else None
        ),
        openai_realtime_voice=(
            agent_settings.openai_realtime_voice if agent_settings else None
        ),
        office_info=office_info,
    )


async def _fetch_runtime_configs(
    db: AsyncSession,
    *,
    tenant_ids: list[str] | None = None,
) -> dict[str, TenantRuntimeConfig]:
    stmt = (
        select(Tenant)
        .where(Tenant.is_active.is_(True))
        .options(selectinload(Tenant.agent_settings))
    )
    if tenant_ids is not None:
        if not tenant_ids:
            return {}
        stmt = stmt.where(Tenant.id.in_(tenant_ids))

    result = await db.execute(stmt.order_by(Tenant.created_at))
    tenants = list(result.scalars().all())
    if not tenants:
        return {}

    ids = [tenant.id for tenant in tenants]
    office_result = await db.execute(select(OfficeConfig).where(OfficeConfig.tenant_id.in_(ids)))
    office_entries = list(office_result.scalars().all())
    office_info_by_tenant: dict[str, dict[str, str]] = {tenant_id: {} for tenant_id in ids}
    for entry in office_entries:
        office_info_by_tenant.setdefault(entry.tenant_id, {})[entry.key] = entry.value

    return {
        tenant.id: _to_runtime_config(tenant, office_info_by_tenant.get(tenant.id, {}))
        for tenant in tenants
    }


def _rebuild_phone_index() -> None:
    _tenant_id_by_phone.clear()
    for config in _configs_by_tenant_id.values():
        if config.twilio_phone_number:
            _tenant_id_by_phone[config.twilio_phone_number] = config.tenant_id


async def warm_all(db: AsyncSession) -> None:
    """Load every active tenant's runtime configuration into memory."""
    configs = await _fetch_runtime_configs(db)
    _configs_by_tenant_id.clear()
    _configs_by_tenant_id.update(configs)

    _fingerprints_by_tenant_id.clear()
    _fingerprints_by_tenant_id.update(
        {tenant_id: _fingerprint(config) for tenant_id, config in configs.items()}
    )
    _rebuild_phone_index()
    logger.info("Tenant runtime cache warmed for %d tenants", len(configs))


async def refresh_all(db: AsyncSession) -> set[str]:
    """Refresh active tenant runtime configs and return the changed tenant ids."""
    configs = await _fetch_runtime_configs(db)
    changed_tenant_ids: set[str] = set()

    for tenant_id, config in configs.items():
        new_fingerprint = _fingerprint(config)
        if _fingerprints_by_tenant_id.get(tenant_id) != new_fingerprint:
            changed_tenant_ids.add(tenant_id)

    removed_tenant_ids = set(_configs_by_tenant_id) - set(configs)
    if removed_tenant_ids:
        changed_tenant_ids.update(removed_tenant_ids)

    _configs_by_tenant_id.clear()
    _configs_by_tenant_id.update(configs)
    _fingerprints_by_tenant_id.clear()
    _fingerprints_by_tenant_id.update(
        {tenant_id: _fingerprint(config) for tenant_id, config in configs.items()}
    )
    _rebuild_phone_index()
    return changed_tenant_ids


async def refresh_tenant(db: AsyncSession, tenant_id: str) -> TenantRuntimeConfig | None:
    """Refresh a single tenant config in memory and return it if active."""
    configs = await _fetch_runtime_configs(db, tenant_ids=[tenant_id])
    config = configs.get(tenant_id)

    if not config:
        _configs_by_tenant_id.pop(tenant_id, None)
        _fingerprints_by_tenant_id.pop(tenant_id, None)
        _rebuild_phone_index()
        return None

    _configs_by_tenant_id[tenant_id] = config
    _fingerprints_by_tenant_id[tenant_id] = _fingerprint(config)
    _rebuild_phone_index()
    return config


def get_tenant_config(tenant_id: str) -> TenantRuntimeConfig | None:
    return _configs_by_tenant_id.get(tenant_id)


def get_tenant_config_by_phone(phone_number: str) -> TenantRuntimeConfig | None:
    tenant_id = _tenant_id_by_phone.get(phone_number)
    if not tenant_id:
        return None
    return _configs_by_tenant_id.get(tenant_id)
