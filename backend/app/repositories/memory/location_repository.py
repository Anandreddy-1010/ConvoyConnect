"""
app/repositories/memory/location_repository.py
--------------------------------------------------
In-memory implementation of LocationRepository.

Only the single latest LocationRecord per rider is retained — each
call to `upsert` overwrites the previous entry for that rider. A
future phase that needs trajectory history (for delay prediction,
route-drift analysis, etc.) will likely add a separate
`LocationHistoryRepository` rather than changing this one, to keep
"current position" lookups cheap.
"""

from typing import Dict, Optional

from app.models.location import LocationRecord
from app.repositories.base import LocationRepository


class InMemoryLocationRepository(LocationRepository):
    def __init__(self) -> None:
        self._latest_by_rider: Dict[str, LocationRecord] = {}

    def upsert(self, location: LocationRecord) -> LocationRecord:
        self._latest_by_rider[location.rider_id] = location
        return location

    def get_latest_for_rider(self, rider_id: str) -> Optional[LocationRecord]:
        return self._latest_by_rider.get(rider_id)

    def get_latest_for_ride(self, ride_id: str) -> Dict[str, LocationRecord]:
        return {
            rider_id: loc
            for rider_id, loc in self._latest_by_rider.items()
            if loc.ride_id == ride_id
        }
