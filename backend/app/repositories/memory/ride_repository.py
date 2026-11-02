"""
app/repositories/memory/ride_repository.py
--------------------------------------------
In-memory implementation of RideRepository.

Storage is a plain dict keyed by ride id, held in process memory. All
data is lost on server restart — this is expected and fine for Phase 2
development/testing. Swap for a Postgres- or Firestore-backed
implementation later without touching any calling code (see
app/repositories/base.py for the interface contract).

Not thread-safe / not safe for multiple worker processes — acceptable
for a single-process dev server.
"""

from typing import Dict, List, Optional

from app.models.ride import RideRecord
from app.repositories.base import RideRepository


class InMemoryRideRepository(RideRepository):
    def __init__(self) -> None:
        self._rides: Dict[str, RideRecord] = {}

    def create(self, ride: RideRecord) -> RideRecord:
        self._rides[ride.id] = ride
        return ride

    def get_by_id(self, ride_id: str) -> Optional[RideRecord]:
        return self._rides.get(ride_id)

    def get_by_invite_code(self, invite_code: str) -> Optional[RideRecord]:
        for ride in self._rides.values():
            if ride.invite_code == invite_code:
                return ride
        return None

    def list_all(self) -> List[RideRecord]:
        return list(self._rides.values())
