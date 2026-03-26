# FleetOS — Transporto priemonių valdymo sistema

Profesionalus web įrankis transporto priemonių duomenų valdymui su automatišku duomenų nuskaitymu iš PDF registracijos liudijimų.

## Funkcijos

- 🚗 **Transporto priemonių sąrašas** — kortelių ir lentelės vaizdas
- 📄 **PDF nuskaitymas** — automatinis duomenų užpildymas iš registracijos liudijimo
- 🔔 **Priminimai** — techninė apžiūra, draudimas, tepalo keitimas
- ✏️ **CRUD** — pridėti, peržiūrėti, redaguoti, ištrinti
- 📊 **Skydelis** — statistika ir artimiausi terminai
- 🔍 **Paieška** — pagal valst. nr, markę, modelį, VIN

## Tech stack

- **Backend**: FastAPI + SQLAlchemy + SQLite
- **Frontend**: Vanilla HTML/CSS/JS (bedeprekia, greitai veikia)
- **Hostingas**: Railway (nemokamas)
- **PDF API**: https://pdf-extractor-api-production-82cc.up.railway.app

---

## Deployment į Railway

### 1. GitHub repozitorija

```bash
git init
git remote add origin https://github.com/vvaidasinfo-source/fleet-manager.git
git add .
git commit -m "Initial commit — FleetOS"
git push -u origin main
```

### 2. Railway (nemokamas planas)

1. Eikite į **https://railway.app** → prisijunkite su GitHub
2. Spauskite **"New Project"** → **"Deploy from GitHub repo"**
3. Pasirinkite `vvaidasinfo-source/fleet-manager`
4. Railway automatiškai aptiks `Dockerfile` ir pradės deploy
5. Eikite į **Settings → Networking → Generate Domain** — gausite nemokamą URL

### 3. Aplinkos kintamieji (neprivaloma)

Railway → Variables:
```
PDF_API_URL=https://pdf-extractor-api-production-82cc.up.railway.app
DATABASE_URL=sqlite:///./fleet.db
```

> **Pastaba dėl duomenų bazės**: SQLite veikia Railway, bet po kiekvieno redeploy duomenys gali būti prarasti. Ilgalaikiams duomenims rekomenduojama Railway PostgreSQL papildinys (taip pat nemokamas iki ~100MB).

### Railway PostgreSQL (rekomenduojama)

1. Railway projekte → **"New"** → **"Database"** → **"PostgreSQL"**
2. Nukopijuokite `DATABASE_URL` iš PostgreSQL aplinkos
3. Pridėkite kaip kintamąjį jūsų Flask app

---

## Lokalus paleidimas

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# Atidarykite: http://localhost:8000
```

---

## PDF API

Sistema naudoja `POST /extract` endpoint su `multipart/form-data`:
```
file: <PDF failas>
```

Grąžina JSON su transporto priemonės duomenimis.
