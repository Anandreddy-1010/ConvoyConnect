"""
app/services/location_service.py
-----------------------------------
Business logic for recording and retrieving GPS location updates.

DISCLAIMER (see also app/schemas/location.py): this service only
stores whatever coordinates are explicitly submitted via
update_location(). There is no device GPS integration, background
polling, or push-based streaming — "real-time" tracking in the sense
of continuous automatic updates is a Phase 3+ goal, not implemented
here. Distance/separation calculations (haversine, drift detection)
are also not implemented yet — see app/geospatial/README.md.
"""

from datetime import timezone
from typing import Dict

from app.core.exceptions import RideNotFoundError
from app.geospatial.separation_detector import detect_rider_status
from app.models.location import LocationRecord
from app.repositories.base import LocationRepository, RideRepository, RiderRepository
from app.schemas.location import LocationUpdateRequest
from app.services.rider_service import RiderService
from app.utils.time_utils import utc_now


class LocationService:
    def __init__(
        self,
        location_repo: LocationRepository,
        rider_repo: RiderRepository,
        ride_repo: RideRepository,
    ):
        self._location_repo = location_repo
        self._rider_repo = rider_repo
        self._ride_repo = ride_repo
        self._rider_service = RiderService(rider_repo, ride_repo)

    def update_location(
        self, ride_id: str, rider_id: str, request: LocationUpdateRequest
    ) -> LocationRecord:
        # Validates the rider belongs to this ride (raises otherwise).
        self._rider_service.get_rider_in_ride(ride_id, rider_id)

        location = LocationRecord(
            rider_id=rider_id,
            ride_id=ride_id,
            latitude=request.latitude,
            longitude=request.longitude,
            speed_kmh=request.speed_kmh,
            heading_deg=request.heading_deg,
        )
        saved_location = self._location_repo.upsert(location)
        self._refresh_rider_statuses(ride_id)
        return saved_location


    def _is_location_fresh(self, location: LocationRecord, now) -> bool:
        recorded_at = location.recorded_at
        if recorded_at.tzinfo is None:
            recorded_at = recorded_at.replace(tzinfo=timezone.utc)

        age_seconds = (now - recorded_at).total_seconds()
        return 0 <= age_seconds <= 120

    def _refresh_rider_statuses(self, ride_id: str) -> None:
        riders = self._rider_repo.list_by_ride(ride_id)
        leader = next((r for r in riders if r.role == "leader"), None)

        if leader is None:
            return

        leader_location = self._location_repo.get_latest_for_rider(leader.id)
        now = utc_now()

        if leader_location is None or not self._is_location_fresh(leader_location, now):
            return

        for rider in riders:
            if rider.id == leader.id:
                continue

            rider_location = self._location_repo.get_latest_for_rider(rider.id)

            if rider_location is None or not self._is_location_fresh(rider_location, now):
                continue

            detected_status = detect_rider_status(
                rider_location.latitude,
                rider_location.longitude,
                leader_location.latitude,
                leader_location.longitude,
                current_status=rider.status,
            )

            if detected_status != rider.status:
                rider.status = detected_status
                self._rider_repo.update(rider)
    def get_group_locations(self, ride_id: str) -> Dict[str, LocationRecord]:
        if self._ride_repo.get_by_id(ride_id) is None:
            raise RideNotFoundError(ride_id)
        return self._location_repo.get_latest_for_ride(ride_id)

    def get_rider_location(self, rider_id: str):
        """Convenience passthrough used when building a single rider's
        RiderResponse (which embeds its latest location, if any)."""
        return self._location_repo.get_latest_for_rider(rider_id)
