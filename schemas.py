from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional


class VehicleBase(BaseModel):
    plate: str
    vin: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    color: Optional[str] = None
    engine: Optional[str] = None
    fuel_type: Optional[str] = None
    body_type: Optional[str] = None
    seats: Optional[int] = None
    owner_name: Optional[str] = None
    owner_address: Optional[str] = None
    mileage: Optional[int] = None
    notes: Optional[str] = None
    tech_inspection_date: Optional[date] = None
    insurance_date: Optional[date] = None
    oil_change_date: Optional[date] = None
    doc_pdf_path: Optional[str] = None


class VehicleCreate(VehicleBase):
    pass


class VehicleUpdate(VehicleBase):
    plate: Optional[str] = None


class VehicleOut(VehicleBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ReminderOut(BaseModel):
    id: int
    vehicle_id: int
    type: str
    due_date: Optional[date] = None
    note: Optional[str] = None

    model_config = {"from_attributes": True}
