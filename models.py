from sqlalchemy import Column, Integer, String, Date, DateTime, Text
from sqlalchemy.sql import func
from database import Base


class Vehicle(Base):
    __tablename__ = "vehicles"

    id              = Column(Integer, primary_key=True, index=True)
    plate           = Column(String(20), unique=True, index=True, nullable=False)
    vin             = Column(String(50), index=True)
    make            = Column(String(100))
    model           = Column(String(100))
    year            = Column(Integer)
    color           = Column(String(50))
    engine          = Column(String(100))
    fuel_type       = Column(String(50))
    body_type       = Column(String(50))
    seats           = Column(Integer)
    owner_name      = Column(String(200))
    owner_address   = Column(Text)
    mileage         = Column(Integer)
    notes           = Column(Text)

    # Dates for reminders
    tech_inspection_date = Column(Date)
    insurance_date       = Column(Date)
    oil_change_date      = Column(Date)

    doc_pdf_path = Column(String(500))   # kelias į išsaugotą PDF

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Reminder(Base):
    __tablename__ = "reminders"

    id         = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, index=True)
    type       = Column(String(50))
    due_date   = Column(Date)
    note       = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
