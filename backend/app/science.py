"""Scientific core. Pure functions, no I/O. Never fabricates values."""
import numpy as np

R_EARTH = 6371008.8  # mean Earth radius, m


def linear_to_db(intensity):
    """NISAR GCOV diagonal intensity (linear gamma0) -> dB. Non-positive/NaN -> NaN."""
    a = np.asarray(intensity, dtype="float64")
    out = np.full(a.shape, np.nan)
    ok = np.isfinite(a) & (a > 0)
    out[ok] = 10.0 * np.log10(a[ok])
    return out


def s1_db_passthrough(db):
    """Sentinel-1 COPERNICUS/S1_GRD is already sigma0 in dB: do NOT apply log10 again."""
    return np.asarray(db, dtype="float64")


def diff_db(before_db, after_db):
    """D = after - before, same sensor + same channel only. NaN where either is invalid."""
    b, a = np.asarray(before_db, float), np.asarray(after_db, float)
    if b.shape != a.shape:
        raise ValueError("Rasters must share one analysis grid")
    return a - b


def check_pair_compatible(before: dict, after: dict):
    """Raise if scenes are not a valid within-sensor, same-channel comparison."""
    for k in ("sensor", "channel", "intensity_convention"):
        if before.get(k) != after.get(k):
            raise ValueError(f"Incompatible scenes: {k} differs ({before.get(k)} vs {after.get(k)})")
    warnings = []
    for k in ("orbit_direction", "relative_orbit"):
        if before.get(k) != after.get(k):
            warnings.append(f"{k} differs: view geometry not matched")
    if before["acquisition_start"] >= after["acquisition_start"]:
        raise ValueError("Before scene must precede after scene")
    return warnings


def pixel_area_m2_geographic(lat_top, dlat_deg, dlon_deg):
    """Authalic spherical area of a lat/lon cell whose top edge is lat_top (deg)."""
    lat1 = np.radians(lat_top)
    lat2 = np.radians(np.asarray(lat_top, float) - dlat_deg)
    return R_EARTH**2 * np.radians(dlon_deg) * np.abs(np.sin(lat1) - np.sin(lat2))


def candidate_change(diff, threshold_db, pixel_area_m2):
    """Candidate surface-change pixels where |D| >= threshold. Exploratory; NOT a fire classifier."""
    d = np.asarray(diff, float)
    valid = np.isfinite(d)
    mask = valid & (np.abs(d) >= threshold_db)
    area = np.broadcast_to(np.asarray(pixel_area_m2, float), d.shape)
    return {"mask": mask, "valid_pixels": int(valid.sum()), "candidate_pixels": int(mask.sum()),
            "analyzed_area_ha": float(area[valid].sum() / 1e4),
            "candidate_change_area_ha": float(area[mask].sum() / 1e4),
            "threshold_db": float(threshold_db),
            "label": "candidate_surface_change (exploratory, unvalidated)"}


def sensitivity(diff, thresholds, pixel_area_m2):
    return [{"threshold_db": t, **{k: v for k, v in candidate_change(diff, t, pixel_area_m2).items() if k != "mask"}}
            for t in thresholds]


def ndvi(nir, red):
    nir, red = np.asarray(nir, float), np.asarray(red, float)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where((nir + red) != 0, (nir - red) / (nir + red), np.nan)


def nbr(nir, swir2):
    return ndvi(nir, swir2)  # (NIR-SWIR2)/(NIR+SWIR2)


def dnbr(nbr_before, nbr_after):
    return np.asarray(nbr_before, float) - np.asarray(nbr_after, float)


MIN_VALIDATION_SAMPLES = 30


def validation_metrics(pred, ref_labels):
    """Metrics only with enough independent labelled samples; 'uncertain' excluded."""
    pairs = [(bool(p), l == "changed") for p, l in zip(pred, ref_labels) if l in ("changed", "unchanged")]
    if len(pairs) < MIN_VALIDATION_SAMPLES:
        return {"status": "Validation not yet available", "n_samples": len(pairs)}
    tp = sum(p and r for p, r in pairs); fp = sum(p and not r for p, r in pairs)
    fn = sum(not p and r for p, r in pairs); tn = sum(not p and not r for p, r in pairs)
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    f1 = 2 * prec * rec / (prec + rec) if prec and rec else None
    return {"status": "computed", "n_samples": len(pairs), "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
            "precision": prec, "recall": rec, "f1": f1}
