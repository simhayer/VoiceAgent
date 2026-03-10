"""Patient lookup and creation."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient


async def lookup_patient(db: AsyncSession, phone: str) -> dict:
    result = await db.execute(select(Patient).where(Patient.phone == phone))
    patient = result.scalars().first()
    if not patient:
        return {"found": False, "message": "No patient found with that phone number."}
    return {
        "found": True,
        "patient_id": patient.id,
        "first_name": patient.first_name,
        "last_name": patient.last_name,
        "phone": patient.phone,
        "insurance_provider": patient.insurance_provider,
    }


async def create_patient(
    db: AsyncSession,
    first_name: str,
    last_name: str,
    phone: str,
    email: str | None = None,
    date_of_birth: str | None = None,
    insurance_provider: str | None = None,
) -> dict:
    result = await db.execute(select(Patient).where(Patient.phone == phone))
    existing = result.scalars().first()
    if existing:
        return {
            "created": False,
            "patient_id": existing.id,
            "message": "Patient with this phone number already exists.",
        }

    patient = Patient(
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        email=email,
        date_of_birth=date_of_birth,
        insurance_provider=insurance_provider,
    )
    db.add(patient)
    await db.commit()
    await db.refresh(patient)

    return {"created": True, "patient_id": patient.id}
