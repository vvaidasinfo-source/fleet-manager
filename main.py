from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import date, timedelta
from typing import Optional
import httpx, os, io, uuid

from database import engine, get_db, Base
from models import Vehicle, Reminder, User
from schemas import (VehicleCreate, VehicleUpdate, VehicleOut, ReminderOut,
                     LoginRequest, TokenResponse, UserCreate, UserUpdate, UserOut)
from auth import (hash_password, verify_password, create_access_token,
                  get_current_user, require_admin, require_editor, require_viewer)

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

app = FastAPI(title="Fleet Manager", version="2.0.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

PDF_API_URL = os.getenv("PDF_API_URL", "https://pdf-extractor-api-production-82cc.up.railway.app")
PDF_DIR = "pdfs"
os.makedirs(PDF_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/pdfs", StaticFiles(directory=PDF_DIR), name="pdfs")

IMAGE_MIME_TYPES = {"image/jpeg","image/jpg","image/png","image/heic","image/heif"}
ALLOWED_EXTENSIONS = {".pdf",".jpg",".jpeg",".png",".heic",".heif"}


# ── Admin init: pirmojo admin sukūrimas ──────────────────────────────────────

def create_default_admin(db: Session):
    if not db.query(User).first():
        admin_user = User(
            username="admin",
            full_name="Administratorius",
            hashed_password=hash_password(os.getenv("ADMIN_PASSWORD", "admin123")),
            role="admin",
        )
        db.add(admin_user)
        db.commit()

@app.on_event("startup")
def startup():
    db = next(get_db())
    create_default_admin(db)


# ── HTML ──────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.post("/api/auth/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username, User.is_active == True).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(401, "Neteisingas vartotojo vardas arba slaptažodis")
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return {"access_token": token, "token_type": "bearer", "user": user}

@app.get("/api/auth/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


# ── Vartotojai (tik admin) ────────────────────────────────────────────────────

@app.get("/api/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _=Depends(require_admin)):
    return db.query(User).order_by(User.created_at).all()

@app.post("/api/users", response_model=UserOut, status_code=201)
def create_user(data: UserCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(400, "Vartotojas jau egzistuoja")
    if data.role not in ["admin", "editor", "viewer"]:
        raise HTTPException(400, "Neteisinga rolė")
    u = User(username=data.username, full_name=data.full_name,
             hashed_password=hash_password(data.password), role=data.role)
    db.add(u); db.commit(); db.refresh(u)
    return u

@app.put("/api/users/{uid}", response_model=UserOut)
def update_user(uid: int, data: UserUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    u = db.query(User).filter(User.id == uid).first()
    if not u:
        raise HTTPException(404, "Vartotojas nerastas")
    if data.full_name is not None: u.full_name = data.full_name
    if data.role is not None:
        if data.role not in ["admin", "editor", "viewer"]:
            raise HTTPException(400, "Neteisinga rolė")
        u.role = data.role
    if data.is_active is not None: u.is_active = data.is_active
    if data.password: u.hashed_password = hash_password(data.password)
    db.commit(); db.refresh(u)
    return u

@app.delete("/api/users/{uid}", status_code=204)
def delete_user(uid: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    if uid == current_user.id:
        raise HTTPException(400, "Negalima ištrinti savęs")
    u = db.query(User).filter(User.id == uid).first()
    if not u:
        raise HTTPException(404, "Vartotojas nerastas")
    db.delete(u); db.commit()


# ── PDF konversija ────────────────────────────────────────────────────────────

def image_bytes_to_pdf_bytes(image_data: bytes) -> bytes:
    img = Image.open(io.BytesIO(image_data))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    page_w, page_h = A4
    img_w, img_h = img.size
    scale = min(page_w / img_w, page_h / img_h)
    draw_w, draw_h = img_w * scale, img_h * scale
    x_offset = (page_w - draw_w) / 2
    y_offset = (page_h - draw_h) / 2
    img_buf = io.BytesIO()
    img.save(img_buf, format="JPEG", quality=95)
    img_buf.seek(0)
    pdf_buf = io.BytesIO()
    c = canvas.Canvas(pdf_buf, pagesize=A4)
    c.drawImage(ImageReader(img_buf), x_offset, y_offset, width=draw_w, height=draw_h, preserveAspectRatio=True)
    c.save()
    pdf_buf.seek(0)
    return pdf_buf.read()


# ── PDF extract ───────────────────────────────────────────────────────────────

@app.post("/api/extract-pdf")
async def extract_pdf(file: UploadFile = File(...), _=Depends(require_editor)):
    content = await file.read()
    filename = (file.filename or "upload").lower()
    content_type = (file.content_type or "").lower()
    ext = os.path.splitext(filename)[1]
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, f"Nepalaikomas formatas '{ext}'")
    is_image = content_type in IMAGE_MIME_TYPES or ext in {".jpg",".jpeg",".png",".heic",".heif"}
    if is_image:
        if ext in {".heic",".heif"} and not HEIC_SUPPORTED:
            raise HTTPException(501, "HEIC neįdiegtas")
        try:
            content = image_bytes_to_pdf_bytes(content)
            filename = os.path.splitext(filename)[0] + ".pdf"
        except Exception as e:
            raise HTTPException(422, f"Konversija nepavyko: {e}")
    pdf_filename = f"{uuid.uuid4()}.pdf"
    with open(os.path.join(PDF_DIR, pdf_filename), "wb") as f:
        f.write(content)
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(f"{PDF_API_URL}/extract",
                                     files={"file": (filename, content, "application/pdf")})
            resp.raise_for_status()
            result = resp.json()
            result["pdf_path"] = f"/pdfs/{pdf_filename}"
            return result
        except httpx.HTTPStatusError as e:
            raise HTTPException(e.response.status_code, str(e))
        except Exception as e:
            raise HTTPException(500, f"PDF API klaida: {e}")


# ── Vehicles ──────────────────────────────────────────────────────────────────

@app.get("/api/vehicles", response_model=list[VehicleOut])
def list_vehicles(search: Optional[str] = None, db: Session = Depends(get_db), _=Depends(require_viewer)):
    q = db.query(Vehicle)
    if search:
        s = f"%{search}%"
        q = q.filter(Vehicle.plate.ilike(s)|Vehicle.make.ilike(s)|Vehicle.model.ilike(s)|Vehicle.vin.ilike(s))
    return q.order_by(Vehicle.created_at.desc()).all()

@app.get("/api/vehicles/{vid}", response_model=VehicleOut)
def get_vehicle(vid: int, db: Session = Depends(get_db), _=Depends(require_viewer)):
    v = db.query(Vehicle).filter(Vehicle.id == vid).first()
    if not v: raise HTTPException(404, "Nerasta")
    return v

@app.get("/api/vehicles/{vid}/pdf")
def get_vehicle_pdf(vid: int, db: Session = Depends(get_db), _=Depends(require_viewer)):
    v = db.query(Vehicle).filter(Vehicle.id == vid).first()
    if not v: raise HTTPException(404, "Nerasta")
    if not v.doc_pdf_path: raise HTTPException(404, "PDF neprikabintas")
    disk_path = v.doc_pdf_path.lstrip("/")
    if not os.path.exists(disk_path): raise HTTPException(404, "PDF failas nerastas")
    return FileResponse(disk_path, media_type="application/pdf",
                        headers={"Content-Disposition": f"inline; filename=vehicle_{vid}.pdf"})

@app.post("/api/vehicles", response_model=VehicleOut, status_code=201)
def create_vehicle(data: VehicleCreate, db: Session = Depends(get_db), _=Depends(require_editor)):
    v = Vehicle(**data.model_dump()); db.add(v); db.commit(); db.refresh(v)
    return v

@app.put("/api/vehicles/{vid}", response_model=VehicleOut)
def update_vehicle(vid: int, data: VehicleUpdate, db: Session = Depends(get_db), _=Depends(require_editor)):
    v = db.query(Vehicle).filter(Vehicle.id == vid).first()
    if not v: raise HTTPException(404, "Nerasta")
    for k, val in data.model_dump(exclude_unset=True).items():
        setattr(v, k, val)
    db.commit(); db.refresh(v)
    return v

@app.delete("/api/vehicles/{vid}", status_code=204)
def delete_vehicle(vid: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    v = db.query(Vehicle).filter(Vehicle.id == vid).first()
    if not v: raise HTTPException(404, "Nerasta")
    db.delete(v); db.commit()


# ── Reminders / Stats ─────────────────────────────────────────────────────────

@app.get("/api/reminders")
def get_reminders(days: int = 30, db: Session = Depends(get_db), _=Depends(require_viewer)):
    today = date.today()
    vehicles = db.query(Vehicle).all()
    alerts = []
    for v in vehicles:
        def check(field_date, label, icon, v=v):
            if field_date:
                delta = (field_date - today).days
                if delta <= days:
                    alerts.append({"vehicle_id": v.id, "plate": v.plate, "make": v.make,
                                   "model": v.model, "type": label, "icon": icon,
                                   "date": field_date.isoformat(), "days_left": delta, "expired": delta < 0})
        check(v.tech_inspection_date, "Techninė apžiūra", "🔧")
        check(v.insurance_date, "Draudimas", "🛡️")
        check(v.oil_change_date, "Tepalo keitimas", "🛢️")
    alerts.sort(key=lambda x: x["days_left"])
    return alerts

@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db), _=Depends(require_viewer)):
    today = date.today()
    threshold = today + timedelta(days=30)
    vehicles = db.query(Vehicle).all()
    total = len(vehicles)
    expired = upcoming = 0
    for v in vehicles:
        for d in [v.tech_inspection_date, v.insurance_date, v.oil_change_date]:
            if d:
                if d < today: expired += 1; break
                elif d <= threshold: upcoming += 1; break
    return {"total": total, "expired": expired, "upcoming_30": upcoming, "ok": total - expired - upcoming}
