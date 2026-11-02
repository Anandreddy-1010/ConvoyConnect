import pytest

from app.geospatial.separation_detector import detect_rider_status


def test_rider_near_leader_is_on_track():
    assert detect_rider_status(12.0, 77.0, 12.001, 77.0) == "on_track"


def test_rider_moderately_far_is_delayed():
    assert detect_rider_status(0, 0, 0, 0.02) == "delayed"


def test_rider_far_from_leader_is_separated():
    assert detect_rider_status(0, 0, 0, 0.1) == "separated"


@pytest.mark.parametrize("status", ["stopped", "sos"])
def test_manual_safety_status_is_preserved(status):
    assert detect_rider_status(0, 0, 0, 0.1, status) == status