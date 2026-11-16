"""Raster catalog + PNG overlays for calibrated Sentinel-1 VH (Aug–Sep 2026).

Study period is derived from data/meta/scene_manifest.csv (verified acquisitions).
Difference product is after − before in dB; not a fire or damage map.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from pathlib import Path

import numpy as np

# Paths are always relative to the repository root (parent of backend/),
# so the app works regardless of OS or where the project is cloned.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW = PROJECT_ROOT / "data" / "raw" / "sentinel1-aug2026"
DEFAULT_PROC = PROJECT_ROOT / "data" / "processed" / "sentinel1-aug2026"
META_DIR = PROJECT_ROOT / "data" / "meta"
MANIFEST = META_DIR / "scene_manifest.csv"

_LAYER_ORDER = ("radar_vh_db", "radar_vh_diff")

_catalog_cache: dict = {"sig": None, "items": None}
_period_cache: dict | None = None


def raw_dir() -> Path:
    return DEFAULT_RAW.resolve()


def proc_dir() -> Path:
    return DEFAULT_PROC.resolve()


def _slug(name: str) -> str:
    stem = Path(name).stem
    h = hashlib.sha1(stem.encode()).hexdigest()[:8]
    clean = re.sub(r"[^a-zA-Z0-9]+", "-", stem).strip("-").lower()
    return f"{clean[:48]}-{h}"


def _short_label(iso_date: str) -> str:
    """Format YYYY-MM-DD → e.g. '23 Aug 2026'."""
    from datetime import date

    d = date.fromisoformat(iso_date)
    return f"{d.day} {d.strftime('%b')} {d.year}"


def _read_manifest() -> list[dict]:
    if not MANIFEST.is_file():
        return []
    with MANIFEST.open(newline="", encoding="utf-8") as fp:
        return list(csv.DictReader(fp))


def study_period() -> dict:
    """Verified before/after dates from manifest + files on disk (no fabrication)."""
    global _period_cache
    if _period_cache is not None:
        return _period_cache

    rows = {r["phase"]: r for r in _read_manifest() if r.get("phase")}
    before_row = rows.get("before")
    after_row = rows.get("after")
    root = raw_dir()

    def present(row: dict | None) -> bool:
        if not row:
            return False
        return (root / row["filename"]).is_file()

    before_date = before_row.get("actual_date_utc") if before_row and present(before_row) else None
    after_date = after_row.get("actual_date_utc") if after_row and present(after_row) else None
    missing = []
    if not before_date:
        missing.append("before")
    if not after_date:
        missing.append("after")

    period = {
        "before_date": before_date,
        "after_date": after_date,
        "before_label": _short_label(before_date) if before_date else None,
        "after_label": _short_label(after_date) if after_date else None,
        "complete": before_date is not None and after_date is not None,
        "missing_phases": missing,
        "before_meta": before_row if before_date else None,
        "after_meta": after_row if after_date else None,
    }
    _period_cache = period
    return period


def clear_caches() -> None:
    global _period_cache
    _period_cache = None
    _catalog_cache["sig"] = None
    _catalog_cache["items"] = None


def _wgs84_bounds(ds) -> dict:
    from rasterio.warp import transform_bounds

    if ds.crs and not ds.crs.is_geographic:
        w, s, e, n = transform_bounds(ds.crs, "EPSG:4326", *ds.bounds, densify_pts=21)
    else:
        b = ds.bounds
        w, s, e, n = b.left, b.bottom, b.right, b.top
    return {
        "bounds": {"west": w, "south": s, "east": e, "north": n},
        "bbox": [w, s, e, n],
    }


def _open_meta(path: Path) -> dict:
    import rasterio

    with rasterio.open(path) as ds:
        b = ds.bounds
        res_x = abs(ds.transform.a)
        res_y = abs(ds.transform.e)
        wgs = _wgs84_bounds(ds)
        if ds.crs and ds.crs.is_geographic:
            mid_lat = (b.bottom + b.top) / 2.0
            m_per_deg_lon = 111_320.0 * abs(np.cos(np.radians(mid_lat)))
            res_m = (res_x * m_per_deg_lon + res_y * 111_320.0) / 2.0
        else:
            res_m = (res_x + res_y) / 2.0
        return {
            "crs": str(ds.crs) if ds.crs else None,
            "width": ds.width,
            "height": ds.height,
            "band_count": ds.count,
            "dtypes": list(ds.dtypes),
            "nodata": ds.nodata,
            "native_bbox": [b.left, b.bottom, b.right, b.top],
            "approx_resolution_m": round(float(res_m), 1),
            "transform": list(ds.transform)[:6],
            "tags": dict(ds.tags()),
            **wgs,
        }


def _dir_sig(*roots: Path):
    parts = []
    for root in roots:
        if not root.is_dir():
            continue
        for p in root.glob("*.tif*"):
            st = p.stat()
            parts.append((str(p), st.st_mtime_ns, st.st_size))
    if MANIFEST.is_file():
        st = MANIFEST.stat()
        parts.append((str(MANIFEST), st.st_mtime_ns, st.st_size))
    return tuple(sorted(parts)) if parts else None


def _catalog_items() -> list[dict]:
    from . import process_aug2026 as P

    try:
        P.ensure_processed()
    except Exception:
        pass

    items = []
    root = raw_dir()
    for row in _read_manifest():
        path = root / row["filename"]
        if not path.is_file():
            continue
        try:
            meta = _open_meta(path)
        except Exception as e:
            items.append({"id": _slug(row["filename"]), "filename": row["filename"], "error": str(e)})
            continue
        phase = row.get("phase")
        actual = row.get("actual_date_utc")
        rid = _slug(path.name)
        items.append(
            {
                "id": rid,
                "filename": path.name,
                "path": str(path),
                "dataset": "sentinel1_aug2026_vh_db",
                "sensor": "Sentinel-1",
                "acquisition_date": actual,
                "acquisition_time_utc": row.get("acquisition_time_utc"),
                "requested_date": row.get("requested_date"),
                "date_status": row.get("date_status"),
                "scene_id": row.get("scene_id"),
                "orbit_pass": row.get("orbit_pass"),
                "relative_orbit": row.get("relative_orbit"),
                "platform": row.get("platform"),
                "phase": phase,
                "overlay_url": f"/api/rasters/{rid}/overlay.png",
                "product_key": f"vh_db_{phase}",
                "polarization": "VH",
                "layer_id": "radar_vh_db",
                "title": "Radar VH (dB)",
                "blurb": (
                    f"Calibrated Sentinel-1 VH backscatter in dB ({actual}). "
                    "Shows radar strength — not confirmed fire damage."
                ),
                "scientifically_calibrated": True,
                "units": "dB",
                "dataset_group": "sentinel1_aug2026_vh_db",
                **meta,
            }
        )

    diff = proc_dir() / "Pengerang_S1_VH_diff_after_minus_before_20m.tif"
    period = study_period()
    if diff.is_file() and period["complete"]:
        try:
            meta = _open_meta(diff)
        except Exception as e:
            items.append({"id": _slug(diff.name), "filename": diff.name, "error": str(e)})
            return items
        rid = _slug(diff.name)
        items.append(
            {
                "id": rid,
                "filename": diff.name,
                "path": str(diff),
                "dataset": "sentinel1_aug2026_vh_diff",
                "sensor": "Sentinel-1",
                "acquisition_date": period["after_date"],
                "overlay_url": f"/api/rasters/{rid}/overlay.png",
                "product_key": "vh_db_diff",
                "polarization": "VH",
                "layer_id": "radar_vh_diff",
                "title": "VH change (dB)",
                "blurb": (
                    f"Calibrated difference ({period['after_label']} minus {period['before_label']}) in dB. "
                    "Radar backscatter change only — not confirmed fire damage."
                ),
                "scientifically_calibrated": True,
                "units": "dB",
                "dataset_group": "sentinel1_aug2026_vh_diff",
                "phase": "difference",
                **meta,
            }
        )
    return items


def catalog() -> list[dict]:
    global _period_cache
    sig = _dir_sig(raw_dir(), proc_dir())
    if _catalog_cache["sig"] == sig and _catalog_cache["items"] is not None:
        return _catalog_cache["items"]
    _period_cache = None
    items = _catalog_items()
    _catalog_cache["sig"] = sig
    _catalog_cache["items"] = items
    return items


def get_by_id(raster_id: str) -> dict | None:
    for item in catalog():
        if item.get("id") == raster_id and "error" not in item:
            return item
    return None


def path_for_id(raster_id: str) -> Path | None:
    item = get_by_id(raster_id)
    if not item:
        return None
    p = Path(item["path"]) if item.get("path") else None
    if p and p.is_file():
        return p
    for root in (raw_dir(), proc_dir()):
        cand = root / item["filename"]
        if cand.is_file():
            return cand
    return None


def layers_for_ui() -> list[dict]:
    period = study_period()
    by_layer: dict[str, dict] = {}
    for i in catalog():
        if "error" in i:
            continue
        lid = i["layer_id"]
        entry = by_layer.setdefault(
            lid,
            {
                "layer_id": lid,
                "title": i["title"],
                "blurb": i["blurb"],
                "dates": {},
                "scientifically_calibrated": bool(i.get("scientifically_calibrated")),
                "dataset_group": i.get("dataset_group"),
            },
        )
        if i.get("acquisition_date"):
            entry["dates"][i["acquisition_date"]] = i["id"]
        # Diff product: same map for either study date (single derived product)
        if lid == "radar_vh_diff" and period["complete"]:
            entry["dates"][period["before_date"]] = i["id"]
            entry["dates"][period["after_date"]] = i["id"]

    def sort_key(x):
        try:
            return (0, _LAYER_ORDER.index(x["layer_id"]))
        except ValueError:
            return (1, x["title"])

    return sorted(by_layer.values(), key=sort_key)


def render_overlay_png(raster_id: str, max_dim: int = 1600) -> bytes:
    import rasterio
    from PIL import Image
    from rasterio.enums import Resampling

    path = path_for_id(raster_id)
    if not path:
        raise FileNotFoundError(raster_id)

    with rasterio.open(path) as ds:
        scale = min(1.0, max_dim / max(ds.width, ds.height))
        out_w = max(1, int(ds.width * scale))
        out_h = max(1, int(ds.height * scale))
        data = ds.read(out_shape=(ds.count, out_h, out_w), resampling=Resampling.bilinear)
        nodata = ds.nodata

        if ds.count >= 3 and str(ds.dtypes[0]) == "uint8":
            rgb = np.transpose(data[:3], (1, 2, 0))
            alpha = np.where(np.any(rgb > 0, axis=2), 255, 0).astype("uint8")
        else:
            band = data[0].astype("float64")
            mask = ~np.isfinite(band)
            if nodata is not None:
                mask |= band == nodata
            valid = band[~mask]
            if valid.size:
                lo, hi = np.percentile(valid, [2, 98])
                if hi <= lo:
                    hi = lo + 1.0
                stretched = np.clip((band - lo) / (hi - lo) * 255.0, 0, 255)
            else:
                stretched = np.zeros_like(band)
            gray = np.where(mask, 0, stretched).astype("uint8")
            rgb = np.stack([gray, gray, gray], axis=-1)
            alpha = np.where(mask, 0, 255).astype("uint8")

        buf = io.BytesIO()
        Image.fromarray(np.dstack([rgb, alpha])).save(buf, format="PNG", optimize=True)
        return buf.getvalue()


def validate_pair(before_id: str, after_id: str) -> dict:
    a = get_by_id(before_id)
    b = get_by_id(after_id)
    if not a or not b:
        missing = [x for x, y in ((before_id, a), (after_id, b)) if not y]
        raise FileNotFoundError(",".join(missing))

    same_grid = (
        a.get("crs") == b.get("crs")
        and a.get("width") == b.get("width")
        and a.get("height") == b.get("height")
        and a.get("transform") == b.get("transform")
        and a.get("native_bbox") == b.get("native_bbox")
    )
    cal_ok = bool(a.get("scientifically_calibrated") and b.get("scientifically_calibrated"))
    orbit_ok = True
    if a.get("orbit_pass") and b.get("orbit_pass"):
        orbit_ok = a.get("orbit_pass") == b.get("orbit_pass") and str(a.get("relative_orbit")) == str(
            b.get("relative_orbit")
        )
    scientific_ok = cal_ok and same_grid and orbit_ok and a.get("units") == "dB" and b.get("units") == "dB"

    return {
        "before_id": a["id"],
        "after_id": b["id"],
        "same_grid": same_grid,
        "orbit_matched": orbit_ok,
        "scientific_db_change_allowed": scientific_ok,
        "visual_comparison_allowed": True,
        "status": "scientific_pair_eligible" if scientific_ok else "visual_comparison_only",
        "plain_message": (
            "Compatible calibrated VH pair (dB). Swipe compares real backscatter images; "
            "change is not confirmed fire damage."
            if scientific_ok
            else "Visual comparison only — pair is not eligible for quantitative dB analysis."
        ),
        "before_acquisition_date": a.get("acquisition_date"),
        "after_acquisition_date": b.get("acquisition_date"),
    }


def _study_aoi() -> dict | None:
    """Provisional search AOI from meta (not a fire perimeter)."""
    import json

    path = META_DIR / "study_area.geojson"
    if not path.is_file():
        return None
    try:
        gj = json.loads(path.read_text(encoding="utf-8"))
        coords = gj["features"][0]["geometry"]["coordinates"][0]
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        return {
            "name": gj["features"][0].get("properties", {}).get("name")
            or "Provisional search AOI — not a fire perimeter",
            "west": min(lons),
            "south": min(lats),
            "east": max(lons),
            "north": max(lats),
            "note": "Analyst search box used to discover scenes. Not a burn boundary.",
        }
    except Exception:
        return None


def _available_scene_note() -> str:
    """Honest note about other catalogued scenes that are not used in the pair."""
    path = META_DIR / "available_scenes.csv"
    if not path.is_file():
        return ""
    rows = []
    with path.open(newline="", encoding="utf-8") as fp:
        rows = list(csv.DictReader(fp))
    unused = [
        r
        for r in rows
        if r.get("date_utc") not in {study_period().get("before_date"), study_period().get("after_date")}
    ]
    if not unused:
        return ""
    bits = [f"{r['date_utc']} ({r.get('pass')}, orbit {r.get('relative_orbit')})" for r in unused]
    return (
        "Other Sentinel-1 scenes exist over the AOI ("
        + "; ".join(bits)
        + ") but are not used because they do not match the DESCENDING relative-orbit 18 pair."
    )


def dataset_summary() -> dict:
    period = study_period()
    items = [i for i in catalog() if "error" not in i]
    dates = sorted({i.get("acquisition_date") for i in items if i.get("acquisition_date")})
    if period["complete"]:
        dates = [period["before_date"], period["after_date"]]

    note_bits = [
        "Workflow: Observe the landscape → Investigate before/after radar change → Understand limits.",
        "Calibrated Sentinel-1 VH backscatter (dB) over Pengerang.",
        "A radar backscatter change is not proof of fire, peat combustion, or cause.",
    ]
    if not period["complete"]:
        note_bits.insert(
            0,
            "Study pair incomplete — missing phase(s): " + ", ".join(period["missing_phases"]) + ".",
        )
    elif period["before_date"] and period["after_date"]:
        note_bits.insert(
            0,
            f"Study acquisitions: {period['before_label']} (pre-event) and {period['after_label']} (post-event).",
        )
    unused_note = _available_scene_note()
    if unused_note:
        note_bits.append(unused_note)

    return {
        "id": "pengerang_earthwatch",
        "title": "Pengerang EarthWatch",
        "subtitle": "Seeing what the clouds hide. Understanding how the land changes.",
        "sensor": "Sentinel-1 (European Space Agency)",
        "place": "Pengerang, Johor, Malaysia",
        "plain_note": " ".join(note_bits),
        "attribution": (
            "Sentinel-1 via Copernicus / ESA; GRD from Google Earth Engine COPERNICUS/S1_GRD. "
            "Map basemap © OpenStreetMap contributors. Independent NASA Space Apps 2026 project; not endorsed by NASA."
        ),
        "count": len(items),
        "acquisition_dates": dates,
        "study_period": {
            "before_date": period["before_date"],
            "after_date": period["after_date"],
            "before_label": period["before_label"],
            "after_label": period["after_label"],
            "complete": period["complete"],
            "missing_phases": period["missing_phases"],
        },
        "case_study": {
            "name": "Pengerang peatland fire (documented report)",
            "location": "Jalan Bypass Punggai–Sebana Cove, Pengerang, Johor",
            "reported_start": "2026-08-24",
            "reported_end": "2026-08-28",
            "reported_area_ha": 51.4,
            "note": (
                "Reported operational figure from public sources. "
                "Not a satellite-derived burn perimeter. Radar products here do not confirm fire damage."
            ),
        },
        "workflow": ["Observe", "Investigate", "Understand"],
        "study_aoi": _study_aoi(),
        "scientifically_calibrated_any": any(i.get("scientifically_calibrated") for i in items),
        "scientifically_calibrated_count": sum(1 for i in items if i.get("scientifically_calibrated")),
        "layers": layers_for_ui(),
        "default_layer_id": "radar_vh_db",
        "limitations": [
            "Only the matched DESCENDING relative-orbit 18 VH pair (23 Aug / 4 Sep 2026) is used for comparison.",
            "Difference is after − before in dB; it is not a burn map or damage score.",
            "PNG map overlays are display stretches of calibrated float rasters; science values remain in GeoTIFF.",
            "NISAR / FIRMS / optical burn indices are not included in this MVP.",
        ],
    }
