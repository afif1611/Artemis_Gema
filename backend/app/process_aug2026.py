"""Process calibrated Sentinel-1 VH dB GeoTIFFs (Aug 23 / Sep 4 2026).

Does not modify originals. Writes float difference + records under data/processed/.
Difference is after − before in dB; not a fire classification.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

# Paths are always relative to the repository root (parent of backend/).
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW = PROJECT_ROOT / "data" / "raw" / "sentinel1-aug2026"
DEFAULT_PROC = PROJECT_ROOT / "data" / "processed" / "sentinel1-aug2026"
META_DIR = PROJECT_ROOT / "data" / "meta"
MANIFEST = META_DIR / "scene_manifest.csv"
NODATA = -9999.0


def raw_dir() -> Path:
    return DEFAULT_RAW.resolve()


def proc_dir() -> Path:
    return DEFAULT_PROC.resolve()


def _read_manifest() -> list[dict]:
    if not MANIFEST.is_file():
        return []
    with MANIFEST.open(newline="", encoding="utf-8") as fp:
        return list(csv.DictReader(fp))


def scene_paths() -> dict[str, Path]:
    """Map phase -> existing GeoTIFF path from manifest (verified on disk)."""
    out = {}
    root = raw_dir()
    for row in _read_manifest():
        name = row.get("filename") or ""
        path = root / name
        if path.is_file():
            out[row["phase"]] = path
    return out


def validate_pair_files(before: Path, after: Path) -> dict:
    import rasterio

    with rasterio.open(before) as b, rasterio.open(after) as a:
        issues = []
        if b.crs != a.crs:
            issues.append(f"CRS mismatch: {b.crs} vs {a.crs}")
        if b.transform != a.transform or b.shape != a.shape:
            issues.append("Grid mismatch (transform/shape)")
        if b.count != 1 or a.count != 1:
            issues.append("Expected single-band rasters")
        for label, ds in (("before", b), ("after", a)):
            if ds.dtypes[0] not in ("float32", "float64"):
                issues.append(f"{label} dtype {ds.dtypes[0]} is not float")
            units = (ds.tags().get("units") or ds.tags(1).get("units") or "").lower()
            if units and units != "db":
                issues.append(f"{label} units tag is {units!r}, expected dB")

        same_grid = not any("mismatch" in i.lower() or "CRS" in i for i in issues)
        return {
            "ok": len(issues) == 0,
            "issues": issues,
            "same_grid": b.crs == a.crs and b.transform == a.transform and b.shape == a.shape,
            "crs": str(b.crs) if b.crs else None,
            "shape": list(b.shape),
            "dtype": b.dtypes[0],
            "nodata": b.nodata,
            "bounds": list(b.bounds),
        }


def compute_difference(before: Path, after: Path, out_tif: Path) -> dict:
    """Write georeferenced float32 difference GeoTIFF (after − before), nodata preserved."""
    import rasterio

    check = validate_pair_files(before, after)
    if not check["same_grid"]:
        raise ValueError("Cannot difference: " + "; ".join(check["issues"] or ["grids differ"]))

    out_tif.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(before) as b, rasterio.open(after) as a:
        bv = b.read(1).astype("float64")
        av = a.read(1).astype("float64")
        nodata = b.nodata if b.nodata is not None else NODATA
        mask = (bv == nodata) | (av == nodata) | ~np.isfinite(bv) | ~np.isfinite(av)
        diff = av - bv
        diff = np.where(mask, nodata, diff).astype("float32")

        profile = b.profile.copy()
        profile.update(dtype="float32", nodata=nodata, compress="deflate")
        with rasterio.open(out_tif, "w", **profile) as dst:
            dst.write(diff, 1)
            dst.update_tags(
                units="dB",
                polarization="VH",
                formula="after_minus_before",
                note="Calibrated VH backscatter difference; not a fire map",
                before_file=before.name,
                after_file=after.name,
            )
            dst.update_tags(1, units="dB", formula="after_minus_before")

        valid = diff[~mask]
        stats = {
            "path": str(out_tif),
            "valid_pixels": int(valid.size),
            "min_db": float(valid.min()) if valid.size else None,
            "max_db": float(valid.max()) if valid.size else None,
            "mean_db": float(valid.mean()) if valid.size else None,
        }
    return {**check, **stats}


def ensure_processed() -> dict:
    """Idempotent: validate pair, write difference + JSON summary if needed."""
    paths = scene_paths()
    if "before" not in paths or "after" not in paths:
        return {"status": "incomplete", "paths": {k: str(v) for k, v in paths.items()}}

    before, after = paths["before"], paths["after"]
    check = validate_pair_files(before, after)
    out = proc_dir()
    out.mkdir(parents=True, exist_ok=True)
    diff_path = out / "Pengerang_S1_VH_diff_after_minus_before_20m.tif"
    summary_path = out / "processing_summary.json"

    if not check["same_grid"]:
        summary = {"status": "blocked", "validation": check}
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return summary

    if not diff_path.is_file():
        result = compute_difference(before, after, diff_path)
    else:
        result = {**check, "path": str(diff_path), "reused": True}

    rows = {r["phase"]: r for r in _read_manifest()}
    summary = {
        "status": "ready",
        "validation": check,
        "difference": {k: result.get(k) for k in ("path", "valid_pixels", "min_db", "max_db", "mean_db", "reused")},
        "scenes": rows,
        "interpretation": (
            "Difference is calibrated VH backscatter change in dB (after − before). "
            "It is not a confirmed burn, fire perimeter, or damage map."
        ),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
