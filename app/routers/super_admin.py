"""Super admin API for managing tenants and their users."""

import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_password, require_super_admin
from app.database import get_db
from app.models.tenant import Tenant
from app.models.user import User

router = APIRouter(prefix="/api/tenants", tags=["super_admin"])


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


class TenantOut(BaseModel):
    id: str
    name: str
    slug: str
    twilio_phone_number: str | None
    timezone: str
    plan: str
    is_active: bool

    model_config = {"from_attributes": True}


class TenantUserCreate(BaseModel):
    email: str
    password: str
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
    return tenant


@router.get("", response_model=list[TenantOut])
async def list_tenants(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin),
):
    result = await db.execute(select(Tenant).order_by(Tenant.created_at))
    return list(result.scalars().all())


@router.get("/{tenant_id}", response_model=TenantOut)
async def get_tenant(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin),
):
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@router.put("/{tenant_id}", response_model=TenantOut)
async def update_tenant(
    tenant_id: str,
    body: TenantUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin),
):
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tenant, field, value)

    await db.commit()
    await db.refresh(tenant)
    return tenant


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
        hashed_password=hash_password(body.password),
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
