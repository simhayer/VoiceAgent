"""Core scheduling engine: availability calculation, conflict detection, booking."""

from datetime import date, datetime, time, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import PROCEDURE_DURATIONS, Appointment
from app.models.provider import Provider
from app.services.cache import get_providers, get_rules


async def get_available_slots(
    db: AsyncSession,
    procedure_type: str,
    date_from: date,
    date_to: date,
    provider_id: str | None = None,
    time_of_day: str | None = None,
    limit: int = 5,
) -> dict:
    """Find open appointment slots across all (or one) providers.

    Uses a single batch query for existing appointments instead of
    per-slot conflict checks (avoids N+1 queries).
    """
    duration = PROCEDURE_DURATIONS.get(procedure_type, 30)
    slot_increment = 30

    providers = get_providers(provider_id)
    provider_ids = [p.id for p in providers]
    all_rules = get_rules(provider_ids)

    date_from_dt = datetime.combine(date_from, time.min)
    date_to_dt = datetime.combine(date_to, time.max)
    appt_stmt = select(Appointment).where(
        Appointment.provider_id.in_(provider_ids),
        Appointment.start_time <= date_to_dt,
        Appointment.end_time >= date_from_dt,
        Appointment.status != "cancelled",
    )
    appt_result = await db.execute(appt_stmt)
    existing_appointments = list(appt_result.scalars().all())

    provider_map = {p.id: p for p in providers}
    all_slots: list[dict] = []
    current_date = date_from

    while current_date <= date_to:
        weekday = current_date.weekday()

        for rule in all_rules:
            if rule.day_of_week != weekday:
                continue

            block_start = _parse_time(rule.start_time)
            block_end = _parse_time(rule.end_time)
            cursor = datetime.combine(current_date, block_start)
            block_end_dt = datetime.combine(current_date, block_end)

            while cursor + timedelta(minutes=duration) <= block_end_dt:
                slot_end = cursor + timedelta(minutes=duration)

                if _slot_matches_time_of_day(cursor, time_of_day) and not _has_conflict_mem(
                    existing_appointments, rule.provider_id, cursor, slot_end
                ):
                    prov = provider_map[rule.provider_id]
                    all_slots.append({
                        "provider_id": prov.id,
                        "provider_name": prov.name,
                        "date": current_date.isoformat(),
                        "start_time": cursor.strftime("%H:%M"),
                        "end_time": slot_end.strftime("%H:%M"),
                        "duration_minutes": duration,
                    })

                cursor += timedelta(minutes=slot_increment)

        current_date += timedelta(days=1)

    return {
        "slots": all_slots[:limit],
        "total_available": len(all_slots),
        "procedure_type": procedure_type,
        "duration_minutes": duration,
    }


async def book_appointment(
    db: AsyncSession,
    provider_id: str,
    procedure_type: str,
    start_time: datetime,
    patient_name: str,
    patient_phone: str,
    patient_id: str | None = None,
    notes: str | None = None,
) -> dict:
    duration = PROCEDURE_DURATIONS.get(procedure_type, 30)
    end_time = start_time + timedelta(minutes=duration)

    conflict_stmt = select(Appointment).where(
        Appointment.provider_id == provider_id,
        Appointment.status != "cancelled",
        and_(Appointment.start_time < end_time, Appointment.end_time > start_time),
    )
    result = await db.execute(conflict_stmt)
    if result.scalars().first():
        return {"success": False, "error": "This time slot is no longer available."}

    prov_result = await db.execute(select(Provider).where(Provider.id == provider_id))
    provider = prov_result.scalars().first()
    if not provider:
        return {"success": False, "error": f"Provider {provider_id} not found."}

    appointment = Appointment(
        provider_id=provider_id,
        patient_id=patient_id,
        start_time=start_time,
        end_time=end_time,
        procedure_type=procedure_type,
        duration_minutes=duration,
        status="scheduled",
        patient_name=patient_name,
        patient_phone=patient_phone,
        notes=notes,
    )
    db.add(appointment)
    await db.commit()
    await db.refresh(appointment)

    return {
        "success": True,
        "appointment_id": appointment.id,
        "provider_name": provider.name,
        "procedure_type": procedure_type,
        "date": start_time.strftime("%A, %B %d, %Y"),
        "time": start_time.strftime("%I:%M %p"),
        "duration_minutes": duration,
    }


async def cancel_appointment(db: AsyncSession, appointment_id: str) -> dict:
    result = await db.execute(select(Appointment).where(Appointment.id == appointment_id))
    appointment = result.scalars().first()
    if not appointment:
        return {"success": False, "error": "Appointment not found."}
    if appointment.status == "cancelled":
        return {"success": False, "error": "Appointment is already cancelled."}

    appointment.status = "cancelled"
    await db.commit()
    return {"success": True, "message": f"Appointment {appointment_id} has been cancelled."}


def _parse_time(t: str) -> time:
    parts = t.split(":")
    return time(int(parts[0]), int(parts[1]))


def _has_conflict_mem(
    appointments: list[Appointment],
    provider_id: str,
    start: datetime,
    end: datetime,
) -> bool:
    """Check for conflicts against an in-memory list of appointments."""
    return any(
        a.provider_id == provider_id and a.start_time < end and a.end_time > start
        for a in appointments
    )


def _slot_matches_time_of_day(dt: datetime, time_of_day: str | None) -> bool:
    if not time_of_day:
        return True
    hour = dt.hour
    if time_of_day == "morning":
        return hour < 12
    if time_of_day == "afternoon":
        return 12 <= hour < 17
    if time_of_day == "evening":
        return hour >= 17
    return True
