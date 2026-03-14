"""Tool definitions for the OpenAI Realtime API function-calling interface."""

import json
from contextvars import ContextVar, Token
from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.office_context import get_office_info as _get_office_info
from app.services.patient_service import lookup_patient as _lookup_patient
from app.services.scheduling import book_appointment as _book_appointment
from app.services.scheduling import get_available_slots as _get_available_slots

_active_db: ContextVar[AsyncSession | None] = ContextVar("active_db", default=None)
_active_tenant_id: ContextVar[str | None] = ContextVar("active_tenant_id", default=None)
_active_tenant_emergency_phone: ContextVar[str | None] = ContextVar("active_tenant_emergency_phone", default=None)
_active_tenant_transfer_phone: ContextVar[str | None] = ContextVar("active_tenant_transfer_phone", default=None)


def set_active_db(db: AsyncSession) -> Token:
    return _active_db.set(db)


def reset_active_db(token: Token):
    _active_db.reset(token)


def set_active_tenant(tenant_id: str) -> Token:
    return _active_tenant_id.set(tenant_id)


def reset_active_tenant(token: Token):
    _active_tenant_id.reset(token)


def set_tenant_phones(emergency: str | None, transfer: str | None) -> tuple[Token, Token]:
    t1 = _active_tenant_emergency_phone.set(emergency)
    t2 = _active_tenant_transfer_phone.set(transfer)
    return t1, t2


def reset_tenant_phones(tokens: tuple[Token, Token]):
    _active_tenant_emergency_phone.reset(tokens[0])
    _active_tenant_transfer_phone.reset(tokens[1])


def _get_db() -> AsyncSession:
    db = _active_db.get()
    if db is None:
        raise RuntimeError("No active database session — set_active_db() must be called first")
    return db


def _get_tenant_id() -> str:
    tid = _active_tenant_id.get()
    if tid is None:
        raise RuntimeError("No active tenant — set_active_tenant() must be called first")
    return tid


# ---------------------------------------------------------------------------
# Tool implementations (plain async functions)
# ---------------------------------------------------------------------------


async def check_availability(
    procedure_type: str,
    date_from: str = "",
    date_to: str = "",
    time_of_day: str = "",
    provider_id: str = "",
    limit: int = 3,
) -> str:
    today = date.today()
    d_from = date.fromisoformat(date_from) if date_from else today
    d_to = date.fromisoformat(date_to) if date_to else today + timedelta(days=7)
    if d_from < today:
        d_from = today

    result = await _get_available_slots(
        db=_get_db(),
        tenant_id=_get_tenant_id(),
        procedure_type=procedure_type,
        date_from=d_from,
        date_to=d_to,
        provider_id=provider_id or None,
        time_of_day=time_of_day or None,
        limit=limit,
    )
    return json.dumps(result)


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
    start_dt = datetime.fromisoformat(f"{date}T{start_time}")
    result = await _book_appointment(
        db=_get_db(),
        tenant_id=_get_tenant_id(),
        provider_id=provider_id,
        procedure_type=procedure_type,
        start_time=start_dt,
        patient_name=patient_name,
        patient_phone=patient_phone,
        patient_id=patient_id or None,
        notes=notes or None,
    )
    return json.dumps(result)


async def get_office_info(query: str) -> str:
    result = await _get_office_info(db=_get_db(), tenant_id=_get_tenant_id(), query=query)
    return json.dumps(result)


async def lookup_patient(phone: str) -> str:
    result = await _lookup_patient(db=_get_db(), tenant_id=_get_tenant_id(), phone=phone)
    return json.dumps(result)


async def escalate(reason: str, urgency: str = "normal") -> str:
    if urgency == "emergency":
        emergency_phone = _active_tenant_emergency_phone.get() or ""
        return json.dumps({
            "action": "transfer",
            "message": "I'm transferring you to our emergency line right now. Please stay on the line.",
            "transfer_number": emergency_phone,
        })
    return json.dumps({
        "action": "message",
        "message": "I've noted your request and a staff member will call you back shortly.",
        "reason": reason,
        "urgency": urgency,
    })


# ---------------------------------------------------------------------------
# OpenAI function definitions (for session.update tools=[...])
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "name": "check_availability",
        "description": (
            "Search for available appointment slots at the dental office. "
            "Call this whenever the patient wants to book or asks about availability."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "procedure_type": {
                    "type": "string",
                    "description": "Type of dental procedure (cleaning, exam, crown, filling, extraction, root_canal, whitening, emergency, consultation)",
                },
                "date_from": {
                    "type": "string",
                    "description": "Start of date range in YYYY-MM-DD format. Defaults to today.",
                },
                "date_to": {
                    "type": "string",
                    "description": "End of date range in YYYY-MM-DD format. Defaults to 7 days from today.",
                },
                "time_of_day": {
                    "type": "string",
                    "description": "Filter by time preference: morning, afternoon, or evening.",
                },
                "provider_id": {
                    "type": "string",
                    "description": "Specific provider ID if patient has a preference.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of slots to return. Default is 3.",
                },
            },
            "required": ["procedure_type"],
        },
    },
    {
        "type": "function",
        "name": "book_appointment",
        "description": "Book a confirmed appointment. You MUST call this tool to finalize any booking — never tell the patient an appointment is booked without calling this first. Only call after the patient has confirmed a specific time slot.",
        "parameters": {
            "type": "object",
            "properties": {
                "provider_id": {"type": "string", "description": "ID of the provider."},
                "procedure_type": {"type": "string", "description": "Type of dental procedure."},
                "date": {"type": "string", "description": "Appointment date in YYYY-MM-DD format."},
                "start_time": {"type": "string", "description": "Start time in HH:MM format (24-hour)."},
                "patient_name": {"type": "string", "description": "Full name of the patient."},
                "patient_phone": {"type": "string", "description": "Patient's phone number."},
                "patient_id": {"type": "string", "description": "Patient ID if found via lookup_patient."},
                "notes": {"type": "string", "description": "Any additional notes."},
            },
            "required": ["provider_id", "procedure_type", "date", "start_time", "patient_name", "patient_phone"],
        },
    },
    {
        "type": "function",
        "name": "get_office_info",
        "description": "Look up information about the dental office — hours, address, insurance, parking, pricing, policies, or any FAQ.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The topic to look up, e.g. 'office hours', 'parking', 'insurance', 'whitening price'.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "lookup_patient",
        "description": "Look up an existing patient record by phone number.",
        "parameters": {
            "type": "object",
            "properties": {
                "phone": {"type": "string", "description": "Patient's phone number to look up."},
            },
            "required": ["phone"],
        },
    },
    {
        "type": "function",
        "name": "escalate",
        "description": "Transfer the call to a staff member or take a message. Use when the patient asks to speak with a person, you cannot answer their question, or there is a dental emergency.",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Why the call is being escalated."},
                "urgency": {
                    "type": "string",
                    "description": "How urgent — normal, urgent, or emergency.",
                    "enum": ["normal", "urgent", "emergency"],
                },
            },
            "required": ["reason"],
        },
    },
]

TOOL_DISPATCH: dict[str, object] = {
    "check_availability": check_availability,
    "book_appointment": book_appointment,
    "get_office_info": get_office_info,
    "lookup_patient": lookup_patient,
    "escalate": escalate,
}
