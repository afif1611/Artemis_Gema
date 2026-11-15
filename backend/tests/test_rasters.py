"""MVP raster catalog / overlay tests."""
import pytest

from app import rasters as R


@pytest.fixture(scope="module")
def has_data():
    return R.raw_dir().is_dir() and any(R.raw_dir().glob("*.tif*"))


def test_dataset_summary(has_data):
    if not has_data:
        pytest.skip("No local GeoTIFFs")
    s = R.dataset_summary()
    assert s["id"] == "sentinel1_jan2026"
    assert s["count"] >= 1
    assert s["scientifically_calibrated_any"] is False
    assert s["layers"]


def test_catalog_not_calibrated(has_data):
    if not has_data:
        pytest.skip("No local GeoTIFFs")
    items = [i for i in R.catalog() if "error" not in i]
    assert items
    assert all(i["scientifically_calibrated"] is False for i in items)
    assert all(i.get("title") for i in items)


def test_pair_visual_only(has_data):
    if not has_data:
        pytest.skip("No local GeoTIFFs")
    layers = R.layers_for_ui()
    layer = next(l for l in layers if "2026-01-23" in l["dates"] and "2026-01-24" in l["dates"])
    result = R.validate_pair(layer["dates"]["2026-01-23"], layer["dates"]["2026-01-24"])
    assert result["visual_comparison_allowed"] is True
    assert result["scientific_db_change_allowed"] is False
    assert result["status"] == "visual_comparison_only"


def test_overlay_png(has_data):
    if not has_data:
        pytest.skip("No local GeoTIFFs")
    item = next(i for i in R.catalog() if i.get("acquisition_date") == "2026-01-23")
    png = R.render_overlay_png(item["id"])
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_friendly_parse():
    info = R._parse("VV_-_decibel_gamma0")
    assert info["polarization"] == "VV"
    assert info["scientifically_calibrated"] is False
    assert "Radar" in info["title"]
