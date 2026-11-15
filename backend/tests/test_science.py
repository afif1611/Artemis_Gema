import numpy as np
import pytest

from app import science as S


def test_linear_to_db_and_invalid():
    out = S.linear_to_db([1.0, 0.1, 0.0, -1, np.nan])
    assert out[0] == 0 and out[1] == pytest.approx(-10)
    assert np.isnan(out[2:]).all()


def test_s1_not_double_converted():
    assert S.s1_db_passthrough([-12.5])[0] == -12.5


def test_diff_and_shape_mismatch():
    assert S.diff_db([-10], [-14])[0] == -4
    with pytest.raises(ValueError):
        S.diff_db(np.zeros((2, 2)), np.zeros((3, 3)))


def test_candidate_area_excludes_nan():
    r = S.candidate_change(np.array([[-5, 0], [np.nan, 4.0]]), 3, 100.0)
    assert r["valid_pixels"] == 3 and r["candidate_pixels"] == 2
    assert r["candidate_change_area_ha"] == pytest.approx(0.02)
    assert r["analyzed_area_ha"] == pytest.approx(0.03)


def test_geographic_area():
    assert S.pixel_area_m2_geographic(1.5, 0.0001, 0.0001) == pytest.approx(11.13**2, rel=0.01)


def test_pair_compatibility():
    b = dict(
        sensor="NISAR",
        channel="HHHH",
        intensity_convention="gamma0",
        acquisition_start="2026-08-01",
    )
    for bad in ({"sensor": "S1"}, {"channel": "HVHV"}, {"acquisition_start": "2026-07-01"}):
        with pytest.raises(ValueError):
            S.check_pair_compatible(b, {**b, **bad})
    assert S.check_pair_compatible(b, {**b, "acquisition_start": "2026-09-01", "relative_orbit": 5})


def test_indices():
    assert S.ndvi(0.5, 0.1) == pytest.approx(0.6667, abs=1e-3)
    assert np.isnan(S.ndvi(0, 0))
    assert S.dnbr(0.5, 0.1) == pytest.approx(0.4)


def test_no_metrics_without_enough_labels():
    r = S.validation_metrics([1, 0], ["changed", "unchanged"])
    assert r["status"] == "Validation not yet available" and "precision" not in r


def test_metrics_with_enough_labels():
    r = S.validation_metrics([1] * 20 + [0] * 20, ["changed"] * 18 + ["unchanged"] * 22)
    assert r["status"] == "computed" and r["confusion"]["tp"] == 18
