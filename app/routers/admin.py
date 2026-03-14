"""Admin REST API for managing dental office data, scoped by tenant."""

import json as _json
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pydantic import BaseModel

from app.auth import get_current_tenant_id, get_current_user
from app.database import get_db
from app.models.appointment import Appointment
from app.models.availability import AvailabilityRule
from app.models.call_log import CallLog, CallMessage
from app.models.office import OfficeConfig
from app.models.patient import Patient
from app.models.provider import Provider
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.appointment import AppointmentCreate, AppointmentOut
from app.schemas.patient import PatientCreate, PatientOut
from app.services import cache as ref_cache
from app.services.scheduling import book_appointment, cancel_appointment

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/providers")
async def list_providers(
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    result = await db.execute(select(Provider).where(Provider.tenant_id == tenant_id))
    providers = result.scalars().all()
    return [
        {"id": p.id, "name": p.name, "title": p.title, "specialties": p.specialties}
        for p in providers
    ]


@router.get("/providers/{provider_id}")
async def get_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    result = await db.execute(
        select(Provider).where(Provider.id == provider_id, Provider.tenant_id == tenant_id)
    )
    provider = result.scalars().first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    rules_result = await db.execute(
        select(AvailabilityRule).where(
            AvailabilityRule.provider_id == provider_id,
            AvailabilityRule.tenant_id == tenant_id,
        )
    )
    rules = rules_result.scalars().all()
    return {
        "id": provider.id,
        "name": provider.name,
        "title": provider.title,
        "specialties": provider.specialties,
        "availability": [
            {"day_of_week": r.day_of_week, "start_time": r.start_time, "end_time": r.end_time}
            for r in rules
        ],
    }


@router.get("/appointments", response_model=list[AppointmentOut])
async def list_appointments(
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    stmt = (
        select(Appointment)
        .options(selectinload(Appointment.provider))
        .where(Appointment.tenant_id == tenant_id)
    )
    if status:
        stmt = stmt.where(Appointment.status == status)
    if date_from:
        stmt = stmt.where(Appointment.start_time >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        stmt = stmt.where(Appointment.start_time <= datetime.combine(date_to, datetime.max.time()))
    stmt = stmt.order_by(Appointment.start_time)
    result = await db.execute(stmt)
    appointments = result.scalars().all()

    results = []
    for a in appointments:
        out = AppointmentOut.model_validate(a)
        out.provider_name = a.provider.name if a.provider else None
        results.append(out)
    return results


@router.post("/appointments/{appointment_id}/cancel")
async def cancel(
    appointment_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    result = await cancel_appointment(db, tenant_id, appointment_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/appointments", response_model=AppointmentOut)
async def create_appointment(
    data: AppointmentCreate,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    # Resolve provider_id from provider_name if needed
    provider_id = data.provider_id
    if not provider_id and data.provider_name:
        result = await db.execute(
            select(Provider).where(
                Provider.tenant_id == tenant_id,
                Provider.name.ilike(f"%{data.provider_name}%"),
            )
        )
        prov = result.scalars().first()
        if prov:
            provider_id = prov.id
    if not provider_id:
        raise HTTPException(status_code=400, detail="provider_id or valid provider_name is required")

    result = await book_appointment(
        db=db,
        tenant_id=tenant_id,
        provider_id=provider_id,
        procedure_type=data.procedure_type,
        start_time=data.start_time,
        patient_name=data.patient_name,
        patient_phone=data.patient_phone,
        notes=data.notes,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])

    # Fetch the full appointment to return AppointmentOut
    stmt = (
        select(Appointment)
        .options(selectinload(Appointment.provider))
        .where(Appointment.id == result["appointment_id"])
    )
    appt = (await db.execute(stmt)).scalars().first()
    out = AppointmentOut.model_validate(appt)
    out.provider_name = appt.provider.name if appt.provider else None
    return out


@router.get("/patients", response_model=list[PatientOut])
async def list_patients(
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    result = await db.execute(select(Patient).where(Patient.tenant_id == tenant_id))
    return list(result.scalars().all())


@router.post("/patients", response_model=PatientOut)
async def create_patient(
    data: PatientCreate,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    result = await db.execute(
        select(Patient).where(Patient.tenant_id == tenant_id, Patient.phone == data.phone)
    )
    if result.scalars().first():
        raise HTTPException(status_code=409, detail="Patient with this phone already exists")
    patient = Patient(tenant_id=tenant_id, **data.model_dump())
    db.add(patient)
    await db.commit()
    await db.refresh(patient)
    return patient


@router.get("/office-config")
async def list_office_config(
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    stmt = select(OfficeConfig).where(OfficeConfig.tenant_id == tenant_id)
    if category:
        stmt = stmt.where(OfficeConfig.category == category)
    result = await db.execute(stmt)
    entries = result.scalars().all()
    return [{"key": e.key, "value": e.value, "category": e.category} for e in entries]


@router.put("/office-config/{key}")
async def upsert_office_config(
    key: str,
    value: str,
    category: str = "general",
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    result = await db.execute(
        select(OfficeConfig).where(OfficeConfig.tenant_id == tenant_id, OfficeConfig.key == key)
    )
    entry = result.scalars().first()
    if entry:
        entry.value = value
        entry.category = category
    else:
        entry = OfficeConfig(tenant_id=tenant_id, key=key, value=value, category=category)
        db.add(entry)
    await db.commit()
    return {"key": key, "value": value, "category": category}


@router.post("/refresh-cache")
async def refresh_cache(
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Re-load providers and availability rules into the in-memory cache for this tenant."""
    await ref_cache.refresh(db, tenant_id)
    return {
        "status": "ok",
        "providers": len(ref_cache.get_providers(tenant_id)),
        "rules": len(ref_cache.get_rules(tenant_id)),
    }


# ── Call Logs ──

@router.get("/call-logs")
async def list_call_logs(
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Return all persisted call sessions with their messages."""
    result = await db.execute(
        select(CallLog)
        .where(CallLog.tenant_id == tenant_id)
        .order_by(CallLog.started_at.desc())
    )
    logs = result.scalars().all()

    out = []
    for log in logs:
        msgs_result = await db.execute(
            select(CallMessage)
            .where(CallMessage.call_log_id == log.id)
            .order_by(CallMessage.sequence)
        )
        msgs = msgs_result.scalars().all()
        out.append({
            "call_sid": log.call_sid,
            "caller_phone": log.caller_phone,
            "status": log.status,
            "started_at": log.started_at.isoformat() if log.started_at else None,
            "ended_at": log.ended_at.isoformat() if log.ended_at else None,
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp.isoformat() if m.timestamp else None,
                    "tool_name": m.tool_name,
                    "tool_args": _json.loads(m.tool_args) if m.tool_args else None,
                }
                for m in msgs
            ],
        })
    return out


# ── Account (self-service tenant profile) ──


class AccountOut(BaseModel):
    id: str
    name: str
    slug: str
    twilio_phone_number: str | None
    cartesia_voice_id: str | None
    greeting_message: str | None
    system_prompt_override: str | None
    emergency_phone: str | None
    transfer_phone: str | None
    timezone: str
    plan: str
    is_active: bool
    user_email: str
    user_role: str

    model_config = {"from_attributes": True}


class AccountUpdate(BaseModel):
    name: str | None = None
    twilio_phone_number: str | None = None
    greeting_message: str | None = None
    system_prompt_override: str | None = None
    emergency_phone: str | None = None
    transfer_phone: str | None = None
    timezone: str | None = None
    line_of_business: str | None = None
    client_count: int | None = None


@router.get("/account", response_model=AccountOut)
async def get_account(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return the current user's tenant profile."""
    result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Also count clients (patients) for this tenant
    patients_result = await db.execute(
        select(Patient).where(Patient.tenant_id == user.tenant_id)
    )
    patient_count = len(patients_result.scalars().all())

    return AccountOut(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        twilio_phone_number=tenant.twilio_phone_number,
        cartesia_voice_id=tenant.cartesia_voice_id,
        greeting_message=tenant.greeting_message,
        system_prompt_override=tenant.system_prompt_override,
        emergency_phone=tenant.emergency_phone,
        transfer_phone=tenant.transfer_phone,
        timezone=tenant.timezone,
        plan=tenant.plan,
        is_active=tenant.is_active,
        user_email=user.email,
        user_role=user.role,
    )


@router.put("/account", response_model=AccountOut)
async def update_account(
    body: AccountUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update the current user's tenant profile (self-service)."""
    result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    update_data = body.model_dump(exclude_unset=True)

    # line_of_business and client_count are stored in office_config, not tenant
    lob = update_data.pop("line_of_business", None)
    client_count = update_data.pop("client_count", None)

    # Check phone uniqueness if changing phone number
    new_phone = update_data.get("twilio_phone_number")
    if new_phone and new_phone != tenant.twilio_phone_number:
        phone_exists = await db.execute(
            select(Tenant).where(
                Tenant.twilio_phone_number == new_phone,
                Tenant.id != tenant.id,
            )
        )
        if phone_exists.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail="Phone number already assigned to another tenant",
            )

    for field, value in update_data.items():
        setattr(tenant, field, value)

    # Persist line_of_business / client_count in office_config
    for config_key, config_value in [
        ("line_of_business", lob),
        ("client_count", client_count),
    ]:
        if config_value is not None:
            cfg_result = await db.execute(
                select(OfficeConfig).where(
                    OfficeConfig.tenant_id == user.tenant_id,
                    OfficeConfig.key == config_key,
                )
            )
            cfg = cfg_result.scalars().first()
            if cfg:
                cfg.value = str(config_value)
            else:
                db.add(
                    OfficeConfig(
                        tenant_id=user.tenant_id,
                        key=config_key,
                        value=str(config_value),
                        category="account",
                    )
                )

    await db.commit()
    await db.refresh(tenant)

    return AccountOut(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        twilio_phone_number=tenant.twilio_phone_number,
        cartesia_voice_id=tenant.cartesia_voice_id,
        greeting_message=tenant.greeting_message,
        system_prompt_override=tenant.system_prompt_override,
        emergency_phone=tenant.emergency_phone,
        transfer_phone=tenant.transfer_phone,
        timezone=tenant.timezone,
        plan=tenant.plan,
        is_active=tenant.is_active,
        user_email=user.email,
        user_role=user.role,
    )
