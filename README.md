# Pengerang EarthWatch (MVP)

Independent project for **NASA Space Apps Challenge 2026** (not endorsed by NASA).

**Seeing what the clouds hide. Understanding how the land changes.**

Interactive FastAPI + Leaflet map of **Pengerang, Johor** using calibrated **Sentinel-1 VH** radar (dB) for a documented peatland fire case study near Jalan Bypass Punggai–Sebana Cove (reported **24–28 Aug 2026**, ~51.4 ha operational figure — not a satellite perimeter).

## Workflow

1. **Observe** — view pre-event (**23 Aug 2026**) or post-event (**4 Sep 2026**) VH backscatter.
2. **Investigate** — swipe-compare the matched pair, or open the VH change (dB) difference layer.
3. **Understand** — radar change is not proof of fire, peat combustion, or cause.

## Run

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. pytest -q
PYTHONPATH=. uvicorn app.main:app --port 8000 --host 127.0.0.1
```

Open **http://127.0.0.1:8000/**

## Data layout

```
data/raw/sentinel1-aug2026/   Verified VH GeoTIFFs (do not overwrite)
data/meta/                    scene_manifest.csv, available_scenes.csv, study_area.geojson
data/processed/               Derived difference GeoTIFF + processing summary
scripts/                      Earth Engine download helper (optional re-fetch)
```

Optional env (see `.env.example`): `RASTER_RAW_PATH`, `RASTER_STORAGE_PATH`.

## Scientific limits

- Only the **DESCENDING relative-orbit 18** VH pair is used for before/after comparison.
- Other scenes listed in `available_scenes.csv` are catalogued but **not** substituted into the pair.
- Difference = after − before in **dB**; PNG overlays are display stretches; float science values stay in GeoTIFF.
- NISAR / FIRMS / optical burn products are **not** in this MVP.
