import pytest

from app.geospatial.distance import haversine_km


def test_same_coordinates_return_zero():
    assert haversine_km(12.0, 77.0, 12.0, 77.0) == 0.0


def test_one_degree_of_longitude_at_equator():
    assert haversine_km(0, 0, 0, 1) == pytest.approx(111.195, abs=0.1)


def test_distance_is_symmetric():
    forward = haversine_km(12.0, 77.0, 13.0, 78.0)
    reverse = haversine_km(13.0, 78.0, 12.0, 77.0)
    assert forward == pytest.approx(reverse)


def test_invalid_latitude_is_rejected():
    with pytest.raises(ValueError):
        haversine_km(91, 0, 0, 0)


def test_invalid_longitude_is_rejected():
    with pytest.raises(ValueError):
        haversine_km(0, 181, 0, 0)


def test_non_finite_coordinates_are_rejected():
    with pytest.raises(ValueError):
        haversine_km(float("nan"), 0, 0, 0)
