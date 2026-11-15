"""Aug–Sep 2026 calibrated Sentinel-1 VH catalog / overlay tests."""
import numpy as np
import pytest

from app import process_aug2026 as P
from app import rasters as R


@pytest.fixture(autouse=True)
def _clear_caches():
    R.clear_caches()
    yield
    R.clear_caches()


@pytest.fixture(scope="module")
def has_aug():
    return R.raw_dir().is_dir() and any(R.raw_dir().glob("*.tif*"))


def test_study_period_from_manifest(has_aug):
    if not has_aug:
        pytest.skip("No August GeoTIFFs")
    period = R.study_period()
    assert period["complete"] is True
    assert period["before_date"] == "2026-08-23"
    assert period["after_date"] == "2026-09-04"
    assert "Aug" in period["before_label"]
    assert "Sep" in period["after_label"]
    assert period["missing_phases"] == []


def test_dataset_summary_aug_only(has_aug):
    if not has_aug:
        pytest.skip("No August GeoTIFFs")
    s = R.dataset_summary()
    assert s["id"] == "pengerang_earthwatch"
    assert s["study_period"]["complete"] is True
    assert s["acquisition_dates"] == ["2026-08-23", "2026-09-04"]
    assert s["scientifically_calibrated_any"] is True
    assert s["default_layer_id"] == "radar_vh_db"
    assert s["workflow"] == ["Observe", "Investigate", "Understand"]
    assert s["case_study"]["reported_area_ha"] == 51.4
    assert s["study_aoi"] is not None
    assert "not a fire" in s["study_aoi"]["name"].lower() or "NOT fire" in s["study_aoi"]["name"]
    assert all("2026-01" not in d for d in s["acquisition_dates"])
    layer_ids = [l["layer_id"] for l in s["layers"]]
    assert "radar_vh_db" in layer_ids
    assert "colour" not in layer_ids
    assert "DESCENDING" in s["plain_note"] or "relative-orbit" in " ".join(s["limitations"])


def test_catalog_calibrated_only(has_aug):
    if not has_aug:
        pytest.skip("No August GeoTIFFs")
    items = [i for i in R.catalog() if "error" not in i]
    assert items
    assert all(i["scientifically_calibrated"] is True for i in items)
    assert all(i["units"] == "dB" for i in items)
    assert all(i["polarization"] == "VH" for i in items)
    assert all(i.get("crs") == "EPSG:32648" for i in items)
    for i in items:
        west, south, east, north = i["bbox"]
        assert 104.0 < west < 104.4
        assert 104.0 < east < 104.4
        assert 1.2 < south < 1.6
        assert 1.2 < north < 1.6


def test_no_january_in_catalog(has_aug):
    if not has_aug:
        pytest.skip("No August GeoTIFFs")
    blob = str(R.catalog()) + str(R.dataset_summary())
    assert "2026-01-23" not in blob
    assert "2026-01-24" not in blob
    assert "january" not in blob.lower()
    assert "sentinel1_jan" not in blob


def test_scientific_pair(has_aug):
    if not has_aug:
        pytest.skip("No August GeoTIFFs")
    period = R.study_period()
    vh = next(l for l in R.layers_for_ui() if l["layer_id"] == "radar_vh_db")
    before = R.get_by_id(vh["dates"][period["before_date"]])
    after = R.get_by_id(vh["dates"][period["after_date"]])
    assert before["acquisition_date"] == "2026-08-23"
    assert after["acquisition_date"] == "2026-09-04"
    assert before["orbit_pass"] == after["orbit_pass"] == "DESCENDING"
    assert str(before["relative_orbit"]) == str(after["relative_orbit"]) == "18"
    result = R.validate_pair(before["id"], after["id"])
    assert result["scientific_db_change_allowed"] is True
    assert result["same_grid"] is True
    assert result["status"] == "scientific_pair_eligible"


def test_processing_and_difference_math(has_aug):
    if not has_aug:
        pytest.skip("No August GeoTIFFs")
    import rasterio

    paths = P.scene_paths()
    assert "before" in paths and "after" in paths
    check = P.validate_pair_files(paths["before"], paths["after"])
    assert check["same_grid"] is True
    assert check["ok"] is True
    summary = P.ensure_processed()
    assert summary["status"] == "ready"
    diff_path = R.proc_dir() / "Pengerang_S1_VH_diff_after_minus_before_20m.tif"
    assert diff_path.is_file()

    with rasterio.open(paths["before"]) as b, rasterio.open(paths["after"]) as a, rasterio.open(diff_path) as d:
        bv, av, dv = b.read(1), a.read(1), d.read(1)
        nodata = b.nodata
        mask = (bv == nodata) | (av == nodata)
        expected = (av.astype("float64") - bv.astype("float64")).astype("float32")
        np.testing.assert_allclose(dv[~mask], expected[~mask], rtol=1e-5, atol=1e-5)
        assert np.all(dv[mask] == nodata)
        assert d.tags().get("units") == "dB"


def test_overlay_png(has_aug):
    if not has_aug:
        pytest.skip("No August GeoTIFFs")
    period = R.study_period()
    item = next(i for i in R.catalog() if i.get("acquisition_date") == period["before_date"])
    png = R.render_overlay_png(item["id"])
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_diff_layer(has_aug):
    if not has_aug:
        pytest.skip("No August GeoTIFFs")
    P.ensure_processed()
    R.clear_caches()
    diffs = [i for i in R.catalog() if i.get("layer_id") == "radar_vh_diff"]
    assert diffs
    png = R.render_overlay_png(diffs[0]["id"])
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
