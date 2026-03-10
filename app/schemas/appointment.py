from datetime import datetime

from pydantic import BaseModel


class AppointmentCreate(BaseModel):
    provider_id: str | None = None
    provider_name: str | None = None
    patient_name: str
    patient_phone: str
    procedure_type: str
    start_time: datetime
    notes: str | None = None


class AppointmentOut(BaseModel):
    id: str
    provider_id: str
    provider_name: str | None = None
    patient_name: str | None
    patient_phone: str | None
    procedure_type: str
    duration_minutes: int
    start_time: datetime
    end_time: datetime
    status: str
    notes: str | None

    model_config = {"from_attributes": True}


class AvailableSlot(BaseModel):
    provider_id: str
    provider_name: str
    date: str
    start_time: str
    end_time: str
    duration_minutes: int
