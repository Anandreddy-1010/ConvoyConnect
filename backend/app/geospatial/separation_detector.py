"""GPS-based rider separation classification."""

from app.geospatial.distance import haversine_km

ON_TRACK_MAX_KM = 1.609344
DELAYED_MAX_KM = 4.828032


def detect_rider_status(
    rider_latitude: float,
    rider_longitude: float,
    leader_latitude: float,
    leader_longitude: float,
    current_status: str = "on_track",
) -> str:
    """Classify a rider by straight-line distance from the group leader."""

    if current_status in ("stopped", "sos"):
        return current_status

    distance = haversine_km(
        rider_latitude, rider_longitude,
        leader_latitude, leader_longitude,
    )

    if distance <= ON_TRACK_MAX_KM:
        return "on_track"
    if distance <= DELAYED_MAX_KM:
        return "delayed"
    return "separated"
