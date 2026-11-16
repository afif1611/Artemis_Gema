# Pengerang EarthWatch (MVP)

Independent project for **NASA Space Apps Challenge 2026** (not endorsed by NASA).

**Seeing what the clouds hide. Understanding how the land changes.**

Interactive FastAPI + Leaflet map of **Pengerang, Johor** using calibrated **Sentinel-1 VH** radar (dB) around a documented peatland fire (reported **24–28 Aug 2026**). Radar change is **not** confirmed fire damage.

## Requirements

- **Python 3.9+** (3.10 or 3.11 recommended)
- About **10 MB** disk for the included GeoTIFF data
- No API keys and **no `.env` file** are required to run the MVP

## Clone and run

```bash
git clone <YOUR_GITHUB_REPO_URL> pengerang-earthwatch
cd pengerang-earthwatch

cd backend
python3 -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows (Command Prompt)
# .venv\Scripts\activate.bat

# Windows (PowerShell)
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt
PYTHONPATH=. pytest -q
PYTHONPATH=. uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000/**

Leave the terminal open while you use the app. Press `Ctrl+C` to stop the server.

## Satellite data (included)

These files ship in the repository (well under GitHub’s 100 MB file limit). You do **not** need to download them separately for a normal run:

| Path | Role |
|---|---|
| `data/raw/sentinel1-aug2026/*_before_*_20m.tif` | Pre-event VH dB (23 Aug 2026) |
| `data/raw/sentinel1-aug2026/*_after_*_20m.tif` | Post-event VH dB (4 Sep 2026) |
| `data/processed/sentinel1-aug2026/*_diff_*_20m.tif` | Derived difference (after − before) |
| `data/meta/scene_manifest.csv` | Verified acquisition metadata |
| `data/meta/available_scenes.csv` | Other scenes over the AOI (not used in the pair) |
| `data/meta/study_area.geojson` | Search AOI outline (not a fire perimeter) |

Do not overwrite the original raw GeoTIFFs. The difference product can be regenerated automatically if missing.

### Optional: re-download with Google Earth Engine

Only needed if you want to recreate the rasters from scratch. Requires a Google Earth Engine project and is **not** part of the normal install:

```bash
pip install earthengine-api requests rasterio
python scripts/pengerang_sentinel1_vh_aug2026_READY.py --project YOUR_EE_PROJECT_ID
```

## Project layout

```
backend/app/          FastAPI API + raster catalog / overlays
backend/tests/        Automated tests
frontend/             Leaflet PWA (served by FastAPI)
data/raw/             Verified Sentinel-1 VH GeoTIFFs
data/meta/            Manifests + study AOI
data/processed/       Derived difference GeoTIFF
scripts/              Optional Earth Engine download helper
```

## Scientific limits

- Only the matched **DESCENDING relative-orbit 18** VH pair (23 Aug / 4 Sep 2026) is used for comparison.
- Other scenes in `available_scenes.csv` are catalogued but **not** substituted into the pair.
- Difference = after − before in **dB**; map PNGs are display stretches; float science values stay in GeoTIFF.
- NISAR / FIRMS / optical burn products are **not** included in this MVP.

## Troubleshooting

| Problem | What to try |
|---|---|
| `pip install` fails on `rasterio` | Use Python 3.10/3.11; upgrade pip (`python -m pip install -U pip`); on Linux you may need GDAL system packages |
| Map says no pictures | Confirm the two GeoTIFFs exist under `data/raw/sentinel1-aug2026/` |
| Port 8000 in use | Stop the other process, or run with `--port 8001` and open that URL |
| Old map after update | Hard-refresh the browser (or clear site data for localhost) |
