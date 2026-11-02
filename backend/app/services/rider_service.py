"""
app/services/rider_service.py
--------------------------------
Business logic for adding riders to a ride, listing them, and updating
rider status.

NOTE: `update_status` currently just persists whatever status the
caller sends. There is no automatic detection of delay/separation
here yet — that is the planned job of app/geospatial (distance/drift
calculations) and app/group_ai (turning raw signals into a status),
which will call into this same repository layer once implemented.
"""

from typing import List

from app.core.exceptions import RideNotFoundError, RiderNotFoundError, RiderNotInRideError
from app.models.rider import RiderRecord
from app.repositories.base import RideRepository, RiderRepository
from app.schemas.rider import RiderAddRequest
from app.utils.ids import generate_id


class RiderService:
    def __init__(self, rider_repo: RiderRepository, ride_repo: RideRepository):
        self._rider_repo = rider_repo
        self._ride_repo = ride_repo

    def add_rider(self, ride_id: str, request: RiderAddRequest) -> RiderRecord:
        if self._ride_repo.get_by_id(ride_id) is None:
            raise RideNotFoundError(ride_id)

        rider = RiderRecord(
            id=generate_id("rider"),
            ride_id=ride_id,
            name=request.name,
            role=request.role.value,
            phone=request.phone,
            bike_model=request.bike_model,
        )
        return self._rider_repo.create(rider)

    def list_riders(self, ride_id: str) -> List[RiderRecord]:
        if self._ride_repo.get_by_id(ride_id) is None:
            raise RideNotFoundError(ride_id)
        return self._rider_repo.list_by_ride(ride_id)

    def get_rider_in_ride(self, ride_id: str, rider_id: str) -> RiderRecord:
        rider = self._rider_repo.get_by_id(rider_id)
        if rider is None:
            raise RiderNotFoundError(rider_id)
        if rider.ride_id != ride_id:
            raise RiderNotInRideError(rider_id, ride_id)
        return rider

    def update_status(self, ride_id: str, rider_id: str, status: str) -> RiderRecord:
        rider = self.get_rider_in_ride(ride_id, rider_id)
        rider.status = status
        return self._rider_repo.update(rider)
