from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import date, timedelta
from typing import Optional
import httpx
import os
import io
import uuid

from database import engine, get_db, Base
from models import Vehicle, Reminder
from schemas import VehicleCreate, VehicleUpdate, VehicleOut, ReminderOut

# HEIC support
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIC_SUPPORTED = True
except ImportError:
    HEIC_SUPPORTED = False

from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Fleet Manager", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PDF_API_URL = os.getenv("PDF_API_URL", "https://pdf-extractor-api-production-82cc.up.railway.app")

PDF_DIR = "pdfs"
os.makedirs(PDF_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/pdfs", StaticFiles(directory=PDF_DIR), name="pdfs")

# Supported image MIME types
IMAGE_MIME_TYPES = {
    "image/jpeg", "image/jpg", "image/png",
    "image/heic", "image/heif",
}

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".heic", ".heif"}


def image_bytes_to_pdf_bytes(image_data: bytes) -> bytes:
    """Convert image bytes (JPG/PNG/HEIC) to PDF bytes using reportlab."""
    img = Image.open(io.BytesIO(image_data))

    # Convert to RGB if needed (HEIC/PNG can be RGBA or other modes)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    # Scale image to fit A4 page
    page_w, page_h = A4
    img_w, img_h = img.size
    scale = min(page_w / img_w, page_h / img_h)
    draw_w = img_w * scale
    draw_h = img_h * scale
    x_offset = (page_w - draw_w) / 2
    y_offset = (page_h - draw_h) / 2

    # Save image as temporary JPEG in memory
    img_buffer = io.BytesIO()
    img.save(img_buffer, format="JPEG", quality=95)
    img_buffer.seek(0)

    # Build PDF in memory
    pdf_buffer = io.BytesIO()
    c = canvas.Canvas(pdf_buffer, pagesize=A4)
    c.drawImage(
        ImageReader(img_buffer), x_offset, y_offset, width=draw_w, height=draw_h,
        preserveAspectRatio=True
    )
    c.save()
    pdf_buffer.seek(0)
    return pdf_buffer.read()


@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()


# ── PDF / Image Extract ───────────────────────────────────────────────────────

@app.post("/api/extract-pdf")
async def extract_pdf(file: UploadFile = File(...)):
    """
    Accept PDF, JPG, PNG, or HEIC files.
    Images are converted to PDF before being sent to the extractor API.
    Converted PDF is saved to disk and path is returned.
    """
    content = await file.read()
    filename = (file.filename or "upload").lower()
    content_type = (file.content_type or "").lower()

    ext = os.path.splitext(filename)[1]
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Nepalaikomas failo formatas '{ext}'. Leistini: PDF, JPG, PNG, HEIC."
        )

    is_image = content_type in IMAGE_MIME_TYPES or ext in {".jpg", ".jpeg", ".png", ".heic", ".heif"}

    if is_image:
        if ext in {".heic", ".heif"} and not HEIC_SUPPORTED:
            raise HTTPException(
                status_code=501,
                detail="HEIC palaikymas neįdiegtas. Įdiekite: pip install pillow-heif"
            )
        try:
            content = image_bytes_to_pdf_bytes(content)
            filename = os.path.splitext(filename)[0] + ".pdf"
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Vaizdo konversija nepavyko: {str(e)}")

    # Išsaugome PDF diske
    pdf_filename = f"{uuid.uuid4()}.pdf"
    pdf_disk_path = os.path.join(PDF_DIR, pdf_filename)
    with open(pdf_disk_path, "wb") as f:
        f.write(content)
    pdf_url_path = f"/pdfs/{pdf_filename}"

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(
                f"{PDF_API_URL}/extract",
                files={"file": (filename, content, "application/pdf")},
            )
            resp.raise_for_status()
            result = resp.json()
            result["pdf_path"] = pdf_url_path  # pridedame PDF kelią prie atsakymo
            return result
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"PDF API klaida: {str(e)}")


@app.get("/api/vehicles/{vid}/pdf")
def get_vehicle_pdf(vid: int, db: Session = Depends(get_db)):
    """Grąžina transporto priemonės PDF dokumentą."""
    v = db.query(Vehicle).filter(Vehicle.id == vid).first()
    if not v:
        raise HTTPException(404, "Vehicle not found")
    if not v.doc_pdf_path:
        raise HTTPException(404, "PDF dokumentas neprikabintas")
    # doc_pdf_path = "/pdfs/uuid.pdf" — pašaliname pirminį "/"
    disk_path = v.doc_pdf_path.lstrip("/")
    if not os.path.exists(disk_path):
        raise HTTPException(404, "PDF failas nerastas diske")
    return FileResponse(disk_path, media_type="application/pdf",
                        headers={"Content-Disposition": f"inline; filename=vehicle_{vid}.pdf"})


# ── Vehicles ─────────────────────────────────────────────────────────────────

@app.get("/api/vehicles", response_model=list[VehicleOut])
def list_vehicles(search: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Vehicle)
    if search:
        s = f"%{search}%"
        q = q.filter(
            Vehicle.plate.ilike(s) |
            Vehicle.make.ilike(s) |
            Vehicle.model.ilike(s) |
            Vehicle.vin.ilike(s)
        )
    return q.order_by(Vehicle.created_at.desc()).all()


@app.get("/api/vehicles/{vid}", response_model=VehicleOut)
def get_vehicle(vid: int, db: Session = Depends(get_db)):
    v = db.query(Vehicle).filter(Vehicle.id == vid).first()
    if not v:
        raise HTTPException(404, "Vehicle not found")
    return v


@app.post("/api/vehicles", response_model=VehicleOut, status_code=201)
def create_vehicle(data: VehicleCreate, db: Session = Depends(get_db)):
    v = Vehicle(**data.model_dump())
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


@app.put("/api/vehicles/{vid}", response_model=VehicleOut)
def update_vehicle(vid: int, data: VehicleUpdate, db: Session = Depends(get_db)):
    v = db.query(Vehicle).filter(Vehicle.id == vid).first()
    if not v:
        raise HTTPException(404, "Vehicle not found")
    for k, val in data.model_dump(exclude_unset=True).items():
        setattr(v, k, val)
    db.commit()
    db.refresh(v)
    return v


@app.delete("/api/vehicles/{vid}", status_code=204)
def delete_vehicle(vid: int, db: Session = Depends(get_db)):
    v = db.query(Vehicle).filter(Vehicle.id == vid).first()
    if not v:
        raise HTTPException(404, "Vehicle not found")
    db.delete(v)
    db.commit()


# ── Reminders / Dashboard ─────────────────────────────────────────────────────

@app.get("/api/reminders")
def get_reminders(days: int = 30, db: Session = Depends(get_db)):
    """Return vehicles with upcoming expiry events within `days` days."""
    today = date.today()
    threshold = today + timedelta(days=days)
    vehicles = db.query(Vehicle).all()
    alerts = []

    for v in vehicles:
        def check(field_date, label, icon):
            if field_date:
                delta = (field_date - today).days
                if delta <= days:
                    alerts.append({
                        "vehicle_id": v.id,
                        "plate": v.plate,
                        "make": v.make,
                        "model": v.model,
                        "type": label,
                        "icon": icon,
                        "date": field_date.isoformat(),
                        "days_left": delta,
                        "expired": delta < 0,
                    })

        check(v.tech_inspection_date, "Techninė apžiūra", "🔧")
        check(v.insurance_date, "Draudimas", "🛡️")
        check(v.oil_change_date, "Tepalo keitimas", "🛢️")

    alerts.sort(key=lambda x: x["days_left"])
    return alerts


@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    today = date.today()
    threshold_30 = today + timedelta(days=30)
    vehicles = db.query(Vehicle).all()
    total = len(vehicles)

    expired = 0
    upcoming = 0
    for v in vehicles:
        for d in [v.tech_inspection_date, v.insurance_date, v.oil_change_date]:
            if d:
                if d < today:
                    expired += 1
                    break
                elif d <= threshold_30:
                    upcoming += 1
                    break

    return {
        "total": total,
        "expired": expired,
        "upcoming_30": upcoming,
        "ok": total - expired - upcoming,
    }