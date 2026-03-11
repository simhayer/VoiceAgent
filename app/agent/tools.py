"""LangGraph tool definitions wrapping the existing service layer."""

import json
from contextvars import ContextVar, Token
from datetime import date, datetime, timedelta

from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.office_context import get_office_info as _get_office_info
from app.services.patient_service import lookup_patient as _lookup_patient
from app.services.scheduling import book_appointment as _book_appointment
from app.services.scheduling import get_available_slots as _get_available_slots

# The db session is injected at runtime via the graph's config.
# Tools receive it from the graph state via a closure.
_active_db: ContextVar[AsyncSession | None] = ContextVar("active_db", default=None)


def set_active_db(db: AsyncSession) -> Token:
    return _active_db.set(db)


def reset_active_db(token: Token):
    _active_db.reset(token)


def _get_db() -> AsyncSession:
    db = _active_db.get()
    if db is None:
        raise RuntimeError("No active database session — set_active_db() must be called before running the agent")
    return db


@tool
async def check_availability(
    procedure_type: str,
    date_from: str = "",
    date_to: str = "",
    time_of_day: str = "",
    provider_id: str = "",
    limit: int = 3,
) -> str:
    """Search for available appointment slots at the dental office.

    Call this whenever the patient wants to book an appointment or asks about availability.
    Use the filter parameters to narrow results based on patient preferences.

    Args:
        procedure_type: Type of dental procedure (cleaning, exam, crown, filling, extraction, root_canal, whitening, emergency, consultation)
        date_from: Start of date range in YYYY-MM-DD format. Defaults to today.
        date_to: End of date range in YYYY-MM-DD format. Defaults to 7 days from today.
        time_of_day: Filter by time preference: morning, afternoon, or evening.
        provider_id: Specific provider ID if patient has a preference.
        limit: Maximum number of slots to return. Default is 3.
    """
    today = date.today()
    d_from = date.fromisoformat(date_from) if date_from else today
    d_to = date.fromisoformat(date_to) if date_to else today + timedelta(days=7)
    if d_from < today:
        d_from = today

    result = await _get_available_slots(
        db=_get_db(),
        procedure_type=procedure_type,
        date_from=d_from,
        date_to=d_to,
        provider_id=provider_id or None,
        time_of_day=time_of_day or None,
        limit=limit,
    )
    return json.dumps(result)


@tool
async def book_appointment(
    provider_id: str,
    procedure_type: str,
    date: str,
    start_time: str,
    patient_name: str,
    patient_phone: str,
    patient_id: str = "",
    notes: str = "",
) -> str:
    """Book a confirmed appointment. Only call this AFTER the patient has confirmed a specific time slot.

    Args:
        provider_id: ID of the provider for the appointment.
        procedure_type: Type of dental procedure.
        date: Appointment date in YYYY-MM-DD format.
        start_time: Start time in HH:MM format (24-hour).
        patient_name: Full name of the patient.
        patient_phone: Patient's phone number.
        patient_id: Patient ID if found via lookup_patient.
        notes: Any additional notes.
    """
    start_dt = datetime.fromisoformat(f"{date}T{start_time}")
    result = await _book_appointment(
        db=_get_db(),
        provider_id=provider_id,
        procedure_type=procedure_type,
        start_time=start_dt,
        patient_name=patient_name,
        patient_phone=patient_phone,
        patient_id=patient_id or None,
        notes=notes or None,
    )
    return json.dumps(result)


@tool
async def get_office_info(query: str) -> str:
    """Look up information about the dental office — hours, address, insurance accepted, parking, pricing, policies, or any FAQ.

    Args:
        query: The topic to look up, e.g. 'office hours', 'parking', 'insurance', 'whitening price'.
    """
    result = await _get_office_info(db=_get_db(), query=query)
    return json.dumps(result)


@tool
async def lookup_patient(phone: str) -> str:
    """Look up an existing patient record by phone number.

    Args:
        phone: Patient's phone number to look up.
    """
    result = await _lookup_patient(db=_get_db(), phone=phone)
    return json.dumps(result)


@tool
async def escalate(reason: str, urgency: str = "normal") -> str:
    """Transfer the call to a staff member or take a message.

    Use when: the patient asks to speak with a person, you cannot answer their question, or there is a dental emergency.

    Args:
        reason: Why the call is being escalated.
        urgency: How urgent — normal, urgent, or emergency.
    """
    if urgency == "emergency":
        return json.dumps({
            "action": "transfer",
            "message": "I'm transferring you to our emergency line right now. Please stay on the line.",
            "transfer_number": "+14155550911",
        })
    return json.dumps({
        "action": "message",
        "message": "I've noted your request and a staff member will call you back shortly.",
        "reason": reason,
        "urgency": urgency,
    })


ALL_TOOLS = [check_availability, book_appointment, get_office_info, lookup_patient, escalate]
