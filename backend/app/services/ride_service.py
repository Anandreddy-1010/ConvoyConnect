"""
app/services/ride_service.py
------------------------------
Business logic for ride creation, joining, and lookup.

The service layer is where rules live that don't belong in either the
API route (HTTP concerns) or the repository (raw storage). API routes
should stay thin: parse the request, call a service method, map the
result/exception to a response.
"""

from typing import Tuple

from app.core.exceptions import InvalidInviteCodeError, RideNotFoundError
from app.models.enums import RiderRole
from app.models.ride import GeoPoint, RideRecord
from app.models.rider import RiderRecord
from app.repositories.base import RideRepository, RiderRepository
from app.schemas.ride import RideCreateRequest, RideJoinRequest
from app.utils.ids import generate_id, generate_invite_code


class RideService:
    def __init__(self, ride_repo: RideRepository, rider_repo: RiderRepository):
        self._ride_repo = ride_repo
        self._rider_repo = rider_repo

    def create_ride(self, request: RideCreateRequest) -> Tuple[RideRecord, RiderRecord]:
        """Creates a new ride and its leader rider in one step. Returns
        both records so the API layer can build a combined response if
        desired."""
        leader = RiderRecord(
            id=generate_id("rider"),
            ride_id="",  # filled in after ride id is known, below
            name=request.leader_name,
            role=RiderRole.LEADER.value,
            phone=request.leader_phone,
            bike_model=request.leader_bike_model,
        )

        ride = RideRecord(
            id=generate_id("ride"),
            name=request.ride_name,
            invite_code=generate_invite_code(),
            created_by_rider_id=leader.id,
            start_location_name=request.start_location_name,
            destination_location_name=request.destination_location_name,
            start_point=GeoPoint(**request.start_point.model_dump()) if request.start_point else GeoPoint(),
            destination_point=(
                GeoPoint(**request.destination_point.model_dump()) if request.destination_point else GeoPoint()
            ),
        )
        leader.ride_id = ride.id

        self._ride_repo.create(ride)
        self._rider_repo.create(leader)
        return ride, leader

    def join_ride(self, request: RideJoinRequest) -> Tuple[RideRecord, RiderRecord]:
        """Adds a rider to an existing ride identified by invite code."""
        ride = self._ride_repo.get_by_invite_code(request.invite_code)
        if ride is None:
            raise InvalidInviteCodeError(request.invite_code)

        rider = RiderRecord(
            id=generate_id("rider"),
            ride_id=ride.id,
            name=request.rider_name,
            role=RiderRole.MEMBER.value,
            phone=request.rider_phone,
            bike_model=request.bike_model,
        )
        self._rider_repo.create(rider)
        return ride, rider

    def get_ride(self, ride_id: str) -> RideRecord:
        ride = self._ride_repo.get_by_id(ride_id)
        if ride is None:
            raise RideNotFoundError(ride_id)
        return ride

    def rider_count(self, ride_id: str) -> int:
        return self._rider_repo.count_for_ride(ride_id)
