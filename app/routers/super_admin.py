"""Super admin API for managing tenants and their users."""

import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.orm import selectinload

from app.auth import require_super_admin
from app.database import get_db
from app.models.tenant import Tenant
from app.models.tenant_agent_settings import TenantAgentSettings
from app.models.user import User
from app.services import active_calls, tenant_runtime

router = APIRouter(prefix="/api/tenants", tags=["super_admin"])


class AgentSettingsOut(BaseModel):
    openai_realtime_model: str | None = None
    openai_realtime_voice: str | None = None
    system_prompt_override: str | None = None


class TenantCreate(BaseModel):
    name: str
    slug: str | None = None
    twilio_phone_number: str | None = None
    cartesia_voice_id: str | None = None
    greeting_message: str | None = None
    system_prompt_override: str | None = None
    emergency_phone: str | None = None
    transfer_phone: str | None = None
    timezone: str = "America/Los_Angeles"
    plan: str = "starter"
    openai_realtime_model: str | None = None
    openai_realtime_voice: str | None = None


class TenantUpdate(BaseModel):
    name: str | None = None
    twilio_phone_number: str | None = None
    cartesia_voice_id: str | None = None
    greeting_message: str | None = None
    system_prompt_override: str | None = None
    emergency_phone: str | None = None
    transfer_phone: str | None = None
    timezone: str | None = None
    plan: str | None = None
    is_active: bool | None = None
    openai_realtime_model: str | None = None
    openai_realtime_voice: str | None = None


class TenantOut(BaseModel):
    id: str
    name: str
    slug: str
    twilio_phone_number: str | None
    timezone: str
    plan: str
    is_active: bool
    greeting_message: str | None = None
    system_prompt_override: str | None = None
    emergency_phone: str | None = None
    transfer_phone: str | None = None
    agent_settings: AgentSettingsOut | None = None

    model_config = {"from_attributes": True}


class TenantUserCreate(BaseModel):
    email: str
    supabase_user_id: str
    role: str = "admin"


class UserOut(BaseModel):
    id: str
    email: str
    role: str
    is_active: bool
    tenant_id: str

    model_config = {"from_attributes": True}


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug.strip("-")


def _tenant_to_out(tenant: Tenant) -> TenantOut:
    return TenantOut(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        twilio_phone_number=tenant.twilio_phone_number,
        timezone=tenant.timezone,
        plan=tenant.plan,
        is_active=tenant.is_active,
        greeting_message=tenant.greeting_message,
        system_prompt_override=tenant.system_prompt_override,
        emergency_phone=tenant.emergency_phone,
        transfer_phone=tenant.transfer_phone,
        agent_settings=AgentSettingsOut(
            openai_realtime_model=tenant.agent_settings.openai_realtime_model,
            openai_realtime_voice=tenant.agent_settings.openai_realtime_voice,
            system_prompt_override=tenant.agent_settings.system_prompt_override,
        )
        if tenant.agent_settings
        else None,
    )


async def _sync_tenant_runtime(db: AsyncSession, tenant_id: str) -> None:
    config = await tenant_runtime.refresh_tenant(db, tenant_id)
    await active_calls.propagate_tenant_config(tenant_id, config)


@router.post("", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: TenantCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin),
):
    slug = body.slug or _slugify(body.name)

    existing = await db.execute(select(Tenant).where(Tenant.slug == slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tenant slug already exists")

    if body.twilio_phone_number:
        phone_exists = await db.execute(
            select(Tenant).where(Tenant.twilio_phone_number == body.twilio_phone_number)
        )
        if phone_exists.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Phone number already assigned to another tenant")

    tenant = Tenant(
        name=body.name,
        slug=slug,
        twilio_phone_number=body.twilio_phone_number,
        cartesia_voice_id=body.cartesia_voice_id,
        greeting_message=body.greeting_message,
        system_prompt_override=body.system_prompt_override,
        emergency_phone=body.emergency_phone,
        transfer_phone=body.transfer_phone,
        timezone=body.timezone,
        plan=body.plan,
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    agent = TenantAgentSettings(
        tenant_id=tenant.id,
        openai_realtime_model=body.openai_realtime_model,
        openai_realtime_voice=body.openai_realtime_voice,
        system_prompt_override=body.system_prompt_override,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(tenant)
    tenant = await db.get(Tenant, tenant.id, options=[selectinload(Tenant.agent_settings)])
    await _sync_tenant_runtime(db, tenant.id)
    return _tenant_to_out(tenant)


@router.get("", response_model=list[TenantOut])
async def list_tenants(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin),
):
    result = await db.execute(
        select(Tenant).order_by(Tenant.created_at).options(selectinload(Tenant.agent_settings))
    )
    return [_tenant_to_out(t) for t in result.scalars().all()]


@router.get("/{tenant_id}", response_model=TenantOut)
async def get_tenant(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin),
):
    result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id).options(selectinload(Tenant.agent_settings))
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return _tenant_to_out(tenant)


@router.put("/{tenant_id}", response_model=TenantOut)
async def update_tenant(
    tenant_id: str,
    body: TenantUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin),
):
    result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id).options(selectinload(Tenant.agent_settings))
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    update_data = body.model_dump(exclude_unset=True)
    agent_fields = {"openai_realtime_model", "openai_realtime_voice", "system_prompt_override"}
    tenant_update = {k: v for k, v in update_data.items() if k not in agent_fields}
    agent_update = {k: v for k, v in update_data.items() if k in agent_fields}

    for field, value in tenant_update.items():
        setattr(tenant, field, value)

    if agent_update:
        if tenant.agent_settings:
            for k, v in agent_update.items():
                setattr(tenant.agent_settings, k, v)
        else:
            db.add(
                TenantAgentSettings(
                    tenant_id=tenant.id,
                    openai_realtime_model=agent_update.get("openai_realtime_model"),
                    openai_realtime_voice=agent_update.get("openai_realtime_voice"),
                    system_prompt_override=agent_update.get("system_prompt_override"),
                )
            )

    await db.commit()
    result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id).options(selectinload(Tenant.agent_settings))
    )
    tenant = result.scalar_one_or_none()
    await _sync_tenant_runtime(db, tenant_id)
    return _tenant_to_out(tenant)


@router.delete("/{tenant_id}")
async def deactivate_tenant(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin),
):
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tenant.is_active = False
    await db.commit()
    await _sync_tenant_runtime(db, tenant_id)
    return {"status": "deactivated", "tenant_id": tenant_id}


@router.post("/{tenant_id}/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_tenant_user(
    tenant_id: str,
    body: TenantUserCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin),
):
    tenant_result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    if not tenant_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Tenant not found")

    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        tenant_id=tenant_id,
        email=body.email,
        supabase_user_id=body.supabase_user_id,
        role=body.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/{tenant_id}/users", response_model=list[UserOut])
async def list_tenant_users(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin),
):
    result = await db.execute(select(User).where(User.tenant_id == tenant_id))
    return list(result.scalars().all())
