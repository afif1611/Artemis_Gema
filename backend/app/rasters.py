"""Local GeoTIFF catalog and PNG overlays for the MVP map.

Files are EO Browser uint8 visualization exports — not calibrated science rasters.
"""
from __future__ import annotations

import hashlib
import io
import os
import re
from pathlib import Path
from typing import Optional

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW = PROJECT_ROOT / "data" / "raw" / "sentinel1-jan2026"

_FNAME_RE = re.compile(
    r"^(?P<start>\d{4}-\d{2}-\d{2})-\d{2}_\d{2}_"
    r"(?P<end>\d{4}-\d{2}-\d{2})-\d{2}_\d{2}_"
    r"Sentinel-1_IW_VV_VH_(?P<product>.+)\.(?:tif|tiff)$",
    re.IGNORECASE,
)

# Friendly labels for ordinary users (product_key → UI)
_FRIENDLY = {
    "enhanced_visualization": {
        "layer_id": "colour",
        "title": "Colour overview",
        "blurb": "A colour picture made from radar. Land, water, and built areas look different.",
    },
    "rgb_ratio": {
        "layer_id": "colour_mix",
        "title": "Colour mix",
        "blurb": "Another colour view that emphasises differences in the radar signal.",
    },
    "sar_urban": {
        "layer_id": "builtup",
        "title": "Built-up highlight",
        "blurb": "Highlights places that often look bright in radar, such as buildings and hard surfaces.",
    },
    "vv_-_decibel_gamma0": {
        "layer_id": "radar_vv",
        "title": "Radar strength (VV)",
        "blurb": "Greyscale radar. Brighter usually means a stronger echo toward the satellite.",
    },
    "vh_-_decibel_gamma0": {
        "layer_id": "radar_vh",
        "title": "Radar strength (VH)",
        "blurb": "Greyscale radar from a different send/receive combo. Useful alongside VV.",
    },
    "vv_-_linear_gamma0": {
        "layer_id": "radar_vv_alt",
        "title": "Radar strength (VV, alt.)",
        "blurb": "Alternative brightness stretch of the VV radar layer.",
    },
    "vh_-_linear_gamma0": {
        "layer_id": "radar_vh_alt",
        "title": "Radar strength (VH, alt.)",
        "blurb": "Alternative brightness stretch of the VH radar layer.",
    },
    "vv_(raw)": {
        "layer_id": "radar_vv_simple",
        "title": "Simple radar (VV)",
        "blurb": "A simpler VV radar preview image.",
    },
    "vh_(raw)": {
        "layer_id": "radar_vh_simple",
        "title": "Simple radar (VH)",
        "blurb": "A simpler VH radar preview image.",
    },
}

DATASET = {
    "id": "sentinel1_jan2026",
    "title": "Pengerang satellite views",
    "subtitle": "Radar pictures from 23 and 24 January 2026",
    "sensor": "Sentinel-1 (European Space Agency)",
    "place": "Pengerang, Johor, Malaysia",
    "plain_note": (
        "These are picture-style satellite layers for exploring the landscape. "
        "They are not measurements of fire, damage, or risk."
    ),
    "attribution": "Sentinel-1 data via Copernicus / ESA. Map basemap © OpenStreetMap contributors.",
}


def raw_dir() -> Path:
    return Path(os.getenv("RASTER_RAW_PATH", str(DEFAULT_RAW))).resolve()


def _slug(name: str) -> str:
    stem = Path(name).stem
    h = hashlib.sha1(stem.encode()).hexdigest()[:8]
    clean = re.sub(r"[^a-zA-Z0-9]+", "-", stem).strip("-").lower()
    return f"{clean[:48]}-{h}"


def _product_key(product: str) -> str:
    return re.sub(r"[\s]+", "_", product.strip()).lower().replace("__", "_")


def _friendly(key: str, product: str) -> dict:
    info = _FRIENDLY.get(key)
    if info:
        return dict(info)
    return {
        "layer_id": key[:32],
        "title": product.replace("_", " "),
        "blurb": "Satellite radar visualization layer.",
    }


def _parse(product: str) -> dict:
    key = _product_key(product)
    pol = None
    m = re.match(r"^(vv|vh)", key)
    if m:
        pol = m.group(1).upper()
    friendly = _friendly(key, product)
    return {
        "product_key": key,
        "polarization": pol,
        "layer_id": friendly["layer_id"],
        "title": friendly["title"],
        "blurb": friendly["blurb"],
        "scientifically_calibrated": False,
        "value_meaning": (
            "Picture brightness values only — not calibrated scientific measurements."
        ),
    }


def _open_meta(path: Path) -> dict:
    import rasterio

    with rasterio.open(path) as ds:
        b = ds.bounds
        res_x = abs(ds.transform.a)
        res_y = abs(ds.transform.e)
        mid_lat = (b.bottom + b.top) / 2.0
        m_per_deg_lat = 111_320.0
        m_per_deg_lon = 111_320.0 * abs(np.cos(np.radians(mid_lat)))
        res_m = (res_x * m_per_deg_lon + res_y * m_per_deg_lat) / 2.0
        return {
            "crs": str(ds.crs) if ds.crs else None,
            "width": ds.width,
            "height": ds.height,
            "band_count": ds.count,
            "dtypes": list(ds.dtypes),
            "bounds": {
                "west": b.left,
                "south": b.bottom,
                "east": b.right,
                "north": b.top,
            },
            "bbox": [b.left, b.bottom, b.right, b.top],
            "approx_resolution_m": round(float(res_m), 1),
            "transform": list(ds.transform)[:6],
        }


def catalog() -> list[dict]:
    root = raw_dir()
    if not root.is_dir():
        return []
    items = []
    for path in sorted(root.glob("*.tif*")):
        if path.name.startswith("."):
            continue
        m = _FNAME_RE.match(path.name)
        product = m.group("product") if m else path.stem
        parsed = _parse(product)
        try:
            meta = _open_meta(path)
        except Exception as e:
            items.append({"id": _slug(path.name), "filename": path.name, "error": str(e)})
            continue
        # uint8 exports are never treated as calibrated
        parsed["scientifically_calibrated"] = False
        rid = _slug(path.name)
        items.append(
            {
                "id": rid,
                "filename": path.name,
                "dataset": DATASET["id"],
                "sensor": "Sentinel-1",
                "acquisition_date": m.group("start") if m else None,
                "overlay_url": f"/api/rasters/{rid}/overlay.png",
                **parsed,
                **meta,
            }
        )
    return items


def get_by_id(raster_id: str) -> Optional[dict]:
    for item in catalog():
        if item.get("id") == raster_id and "error" not in item:
            return item
    return None


def path_for_id(raster_id: str) -> Optional[Path]:
    item = get_by_id(raster_id)
    return (raw_dir() / item["filename"]) if item else None


def layers_for_ui() -> list[dict]:
    """Unique layer types available on both dates when possible."""
    items = [i for i in catalog() if "error" not in i]
    by_layer: dict[str, dict] = {}
    for i in items:
        lid = i["layer_id"]
        entry = by_layer.setdefault(
            lid,
            {
                "layer_id": lid,
                "title": i["title"],
                "blurb": i["blurb"],
                "dates": {},
            },
        )
        entry["dates"][i["acquisition_date"]] = i["id"]
    # Prefer layers that exist on at least one date; sort with colour first
    order = ["colour", "radar_vv", "radar_vh", "builtup", "colour_mix"]
    out = list(by_layer.values())

    def sort_key(x):
        try:
            return (0, order.index(x["layer_id"]))
        except ValueError:
            return (1, x["title"])

    out.sort(key=sort_key)
    return out


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
        if ds.count >= 3:
            rgb = np.transpose(data[:3], (1, 2, 0))
        else:
            band = data[0]
            rgb = np.stack([band, band, band], axis=-1)

        if rgb.dtype != np.uint8:
            flat = rgb.astype("float64")
            valid = np.isfinite(flat)
            if valid.any():
                lo, hi = np.percentile(flat[valid], [2, 98])
                if hi <= lo:
                    hi = lo + 1
                flat = np.clip((flat - lo) / (hi - lo) * 255, 0, 255)
            rgb = np.where(valid, flat, 0).astype("uint8")

        alpha = np.where(np.any(rgb > 0, axis=2), 255, 0).astype("uint8")
        img = Image.fromarray(np.dstack([rgb, alpha]))
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
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
        and a.get("bbox") == b.get("bbox")
    )
    calibrated = a["scientifically_calibrated"] and b["scientifically_calibrated"]
    scientific_ok = calibrated and same_grid
    return {
        "before_id": a["id"],
        "after_id": b["id"],
        "same_grid": same_grid,
        "scientific_db_change_allowed": scientific_ok,
        "visual_comparison_allowed": True,
        "status": "visual_comparison_only" if not scientific_ok else "scientific_pair_eligible",
        "plain_message": (
            "You can slide to compare the two pictures. "
            "This is a visual compare only — not a damage or fire measurement."
        ),
    }


def dataset_summary() -> dict:
    items = [i for i in catalog() if "error" not in i]
    dates = sorted({i.get("acquisition_date") for i in items if i.get("acquisition_date")})
    return {
        **DATASET,
        "count": len(items),
        "acquisition_dates": dates,
        "scientifically_calibrated_any": False,
        "layers": layers_for_ui(),
    }
