"""
app/api/v1/endpoints/riders.py
----------------------------------
Rider-level endpoints, nested under a ride:

  POST  /api/v1/rides/{ride_id}/riders                add a rider directly
  GET   /api/v1/rides/{ride_id}/riders                list riders in a ride
  PATCH /api/v1/rides/{ride_id}/riders/{rider_id}/status   update rider status

NOTE on status updates: the caller sets the status explicitly (e.g. a
test script, or later the rider's own app reporting "I've stopped").
Automatic detection of delay/separation from GPS data is not
implemented in Phase 2 — see app/geospatial/README.md and
app/group_ai/README.md.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_location_service, get_rider_service
from app.core.exceptions import RideNotFoundError, RiderNotFoundError, RiderNotInRideError
from app.schemas.rider import RiderAddRequest, RiderResponse, RiderStatusUpdateRequest
from app.services.location_service import LocationService
from app.services.mappers import rider_to_response
from app.services.rider_service import RiderService

router = APIRouter()


@router.post(
    "/{ride_id}/riders",
    response_model=RiderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a rider to a ride",
)
def add_rider(
    ride_id: str,
    request: RiderAddRequest,
    rider_service: RiderService = Depends(get_rider_service),
) -> RiderResponse:
    try:
        rider = rider_service.add_rider(ride_id, request)
    except RideNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return rider_to_response(rider)


@router.get(
    "/{ride_id}/riders",
    response_model=List[RiderResponse],
    summary="List all riders in a ride",
)
def list_riders(
    ride_id: str,
    rider_service: RiderService = Depends(get_rider_service),
    location_service: LocationService = Depends(get_location_service),
) -> List[RiderResponse]:
    try:
        riders = rider_service.list_riders(ride_id)
    except RideNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return [
        rider_to_response(rider, latest_location=location_service.get_rider_location(rider.id))
        for rider in riders
    ]


@router.patch(
    "/{ride_id}/riders/{rider_id}/status",
    response_model=RiderResponse,
    summary="Update a rider's status",
)
def update_rider_status(
    ride_id: str,
    rider_id: str,
    request: RiderStatusUpdateRequest,
    rider_service: RiderService = Depends(get_rider_service),
    location_service: LocationService = Depends(get_location_service),
) -> RiderResponse:
    try:
        rider = rider_service.update_status(ride_id, rider_id, request.status.value)
    except (RiderNotFoundError, RiderNotInRideError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return rider_to_response(rider, latest_location=location_service.get_rider_location(rider.id))
