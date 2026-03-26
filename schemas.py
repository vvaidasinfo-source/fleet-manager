from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"

class UserBase(BaseModel):
    username: str
    full_name: Optional[str] = None
    role: str = "viewer"

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None

class UserOut(UserBase):
    id: int
    is_active: bool
    created_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


# ── Vehicles ──────────────────────────────────────────────────────────────────

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


# ── Reminders ─────────────────────────────────────────────────────────────────

class ReminderOut(BaseModel):
    id: int
    vehicle_id: int
    type: str
    due_date: Optional[date] = None
    note: Optional[str] = None
    model_config = {"from_attributes": True}
