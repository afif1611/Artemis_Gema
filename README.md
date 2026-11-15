# Pengerang EarthWatch (MVP)

A simple map to explore **Sentinel-1** radar pictures of **Pengerang, Johor** from **23 and 24 January 2026**.

Pick a date, choose a layer, adjust picture strength, or slide-compare the two days. Layers are visualization exports — not fire, damage, or risk measurements.

## Run

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. pytest -q
PYTHONPATH=. uvicorn app.main:app --port 8000 --host 127.0.0.1
```

Open **http://127.0.0.1:8000/**

On a phone (same Wi‑Fi), use `--host 0.0.0.0` and open `http://YOUR_MAC_IP:8000/`.

## Layout

```
backend/app/          FastAPI + raster catalog/overlays
backend/tests/        pytest
frontend/             Leaflet PWA (HTML/CSS/JS)
data/raw/sentinel1-jan2026/   GeoTIFF inputs (local)
```

## Data

Place GeoTIFFs in `data/raw/sentinel1-jan2026/`. Optional: set `RASTER_RAW_PATH` in `.env` (see `.env.example`).
