"""
app/api/v1/endpoints/rides.py
--------------------------------
Ride-level endpoints:

  POST /api/v1/rides            create a new ride (+ its leader)
  POST /api/v1/rides/join       join an existing ride via invite code
  GET  /api/v1/rides/{ride_id}  fetch ride details

Routes stay thin: validate via Pydantic (automatic), call the service,
map exceptions to HTTP errors, map the result to a response schema.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_ride_service
from app.core.exceptions import InvalidInviteCodeError, RideNotFoundError
from app.schemas.ride import RideCreateRequest, RideJoinRequest, RideResponse
from app.schemas.rider import RiderResponse
from app.services.mappers import ride_to_response, rider_to_response
from app.services.ride_service import RideService
from pydantic import BaseModel

router = APIRouter()


class RideJoinResponse(BaseModel):
    """Combined response returned after successfully joining a ride —
    the frontend needs both the ride context and the new rider's id."""

    ride: RideResponse
    rider: RiderResponse


@router.post(
    "",
    response_model=RideResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new group ride",
)
def create_ride(
    request: RideCreateRequest,
    ride_service: RideService = Depends(get_ride_service),
) -> RideResponse:
    ride, _leader = ride_service.create_ride(request)
    return ride_to_response(ride, rider_count=ride_service.rider_count(ride.id))


@router.post(
    "/join",
    response_model=RideJoinResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Join an existing ride using its invite code",
)
def join_ride(
    request: RideJoinRequest,
    ride_service: RideService = Depends(get_ride_service),
) -> RideJoinResponse:
    try:
        ride, rider = ride_service.join_ride(request)
    except InvalidInviteCodeError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return RideJoinResponse(
        ride=ride_to_response(ride, rider_count=ride_service.rider_count(ride.id)),
        rider=rider_to_response(rider),
    )


@router.get(
    "/{ride_id}",
    response_model=RideResponse,
    summary="Get ride details",
)
def get_ride(
    ride_id: str,
    ride_service: RideService = Depends(get_ride_service),
) -> RideResponse:
    try:
        ride = ride_service.get_ride(ride_id)
    except RideNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return ride_to_response(ride, rider_count=ride_service.rider_count(ride_id))
