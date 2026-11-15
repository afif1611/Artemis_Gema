# Pengerang EarthWatch (MVP)
A simple map to explore Sentinel-1 radar pictures of **Pengerang, Johor** from **23 and 24 January 2026**.

Built for beginners: pick a date, choose a layer, optionally slide-compare the two days. Pictures are visualization exports — not fire, damage, or risk measurements.

## Run
```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. pytest -q
PYTHONPATH=. uvicorn app.main:app --port 8000 --host 127.0.0.1
```
Open **http://127.0.0.1:8000/**

## Data
Place GeoTIFFs in `data/raw/sentinel1-jan2026/`.
