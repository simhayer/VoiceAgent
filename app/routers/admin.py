"""Admin REST API for managing the dental office data."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.appointment import Appointment
from app.models.availability import AvailabilityRule
from app.models.call_log import CallLog, CallMessage
from app.models.office import OfficeConfig
from app.models.patient import Patient
from app.models.provider import Provider
from app.schemas.appointment import AppointmentOut
from app.schemas.patient import PatientCreate, PatientOut
from app.services.scheduling import cancel_appointment

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/providers")
async def list_providers(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Provider))
    providers = result.scalars().all()
    return [
        {"id": p.id, "name": p.name, "title": p.title, "specialties": p.specialties}
        for p in providers
    ]


@router.get("/providers/{provider_id}")
async def get_provider(provider_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    provider = result.scalars().first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    rules_result = await db.execute(
        select(AvailabilityRule).where(AvailabilityRule.provider_id == provider_id)
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
):
    stmt = select(Appointment)
    if status:
        stmt = stmt.where(Appointment.status == status)
    if date_from:
        stmt = stmt.where(Appointment.start_time >= date_from.isoformat())
    if date_to:
        stmt = stmt.where(Appointment.start_time <= date_to.isoformat() + "T23:59:59")
    stmt = stmt.order_by(Appointment.start_time)
    result = await db.execute(stmt)
    appointments = result.scalars().all()

    results = []
    for a in appointments:
        prov_result = await db.execute(select(Provider).where(Provider.id == a.provider_id))
        provider = prov_result.scalars().first()
        out = AppointmentOut.model_validate(a)
        out.provider_name = provider.name if provider else None
        results.append(out)
    return results


@router.post("/appointments/{appointment_id}/cancel")
async def cancel(appointment_id: str, db: AsyncSession = Depends(get_db)):
    result = await cancel_appointment(db, appointment_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/patients", response_model=list[PatientOut])
async def list_patients(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Patient))
    return list(result.scalars().all())


@router.post("/patients", response_model=PatientOut)
async def create_patient(data: PatientCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Patient).where(Patient.phone == data.phone))
    if result.scalars().first():
        raise HTTPException(status_code=409, detail="Patient with this phone already exists")
    patient = Patient(**data.model_dump())
    db.add(patient)
    await db.commit()
    await db.refresh(patient)
    return patient


@router.get("/office-config")
async def list_office_config(category: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(OfficeConfig)
    if category:
        stmt = stmt.where(OfficeConfig.category == category)
    result = await db.execute(stmt)
    entries = result.scalars().all()
    return [{"key": e.key, "value": e.value, "category": e.category} for e in entries]


@router.put("/office-config/{key}")
async def upsert_office_config(key: str, value: str, category: str = "general", db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(OfficeConfig).where(OfficeConfig.key == key))
    entry = result.scalars().first()
    if entry:
        entry.value = value
        entry.category = category
    else:
        entry = OfficeConfig(key=key, value=value, category=category)
        db.add(entry)
    await db.commit()
    return {"key": key, "value": value, "category": category}


# ── Call Logs ──

@router.get("/call-logs")
async def list_call_logs(db: AsyncSession = Depends(get_db)):
    """Return all persisted call sessions with their messages."""
    import json as _json
    result = await db.execute(
        select(CallLog).order_by(CallLog.started_at.desc())
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
