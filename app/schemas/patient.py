from pydantic import BaseModel


class PatientCreate(BaseModel):
    first_name: str
    last_name: str
    phone: str
    email: str | None = None
    date_of_birth: str | None = None
    insurance_provider: str | None = None


class PatientOut(BaseModel):
    id: str
    first_name: str
    last_name: str
    phone: str
    email: str | None
    date_of_birth: str | None
    insurance_provider: str | None

    model_config = {"from_attributes": True}
