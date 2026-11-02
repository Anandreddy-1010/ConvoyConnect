"""
app/repositories/memory/rider_repository.py
---------------------------------------------
In-memory implementation of RiderRepository. See ride_repository.py
for general notes on the in-memory storage approach.
"""

from typing import Dict, List, Optional

from app.models.rider import RiderRecord
from app.repositories.base import RiderRepository


class InMemoryRiderRepository(RiderRepository):
    def __init__(self) -> None:
        self._riders: Dict[str, RiderRecord] = {}

    def create(self, rider: RiderRecord) -> RiderRecord:
        self._riders[rider.id] = rider
        return rider

    def get_by_id(self, rider_id: str) -> Optional[RiderRecord]:
        return self._riders.get(rider_id)

    def list_by_ride(self, ride_id: str) -> List[RiderRecord]:
        return [r for r in self._riders.values() if r.ride_id == ride_id]

    def update(self, rider: RiderRecord) -> RiderRecord:
        self._riders[rider.id] = rider
        return rider

    def count_for_ride(self, ride_id: str) -> int:
        return len(self.list_by_ride(ride_id))
