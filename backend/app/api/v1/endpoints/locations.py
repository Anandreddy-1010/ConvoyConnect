"""
app/api/v1/endpoints/locations.py
-------------------------------------
GPS location endpoints, nested under a ride:

  PUT /api/v1/rides/{ride_id}/riders/{rider_id}/location   submit a GPS update
  GET /api/v1/rides/{ride_id}/locations                    latest group positions

DISCLAIMER: These endpoints store/return whatever coordinates are
explicitly submitted by a client. There is no live device GPS
integration, background polling, or streaming â€” this is NOT real-time
tracking yet. A rider's app (or a test script) must call PUT with a
fresh coordinate for their position to update at all. See
app/geospatial/README.md for the Phase 3 plan.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_location_service, get_rider_service
from app.core.exceptions import RideNotFoundError, RiderNotFoundError, RiderNotInRideError
from app.schemas.location import GroupLocationsResponse, LocationUpdateRequest, LocationUpdateResponse, RiderLocationEntry
from app.schemas.common import GeoPointSchema
from app.services.location_service import LocationService
from app.services.mappers import location_to_response
from app.services.rider_service import RiderService
from app.utils.time_utils import utc_now
from app.geospatial.distance import haversine_km

router = APIRouter()


@router.put(
    "/{ride_id}/riders/{rider_id}/location",
    response_model=LocationUpdateResponse,
    summary="Submit a GPS location update for a rider",
)
def update_rider_location(
    ride_id: str,
    rider_id: str,
    request: LocationUpdateRequest,
    location_service: LocationService = Depends(get_location_service),
) -> LocationUpdateResponse:
    try:
        location = location_service.update_location(ride_id, rider_id, request)
    except (RiderNotFoundError, RiderNotInRideError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return location_to_response(location)


@router.get(
    "/{ride_id}/locations",
    response_model=GroupLocationsResponse,
    summary="Get the latest known location for every rider in a ride",
)
def get_group_locations(
    ride_id: str,
    location_service: LocationService = Depends(get_location_service),
    rider_service: RiderService = Depends(get_rider_service),
) -> GroupLocationsResponse:
    try:
        latest_by_rider = location_service.get_group_locations(ride_id)
        riders = rider_service.list_riders(ride_id)
    except RideNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    leader = next((rider for rider in riders if rider.role == "leader"), None)
    leader_location = latest_by_rider.get(leader.id) if leader else None

    entries = []
    for rider in riders:
        loc = latest_by_rider.get(rider.id)

        distance_from_leader = None
        if loc is not None and leader_location is not None:
            distance_from_leader = haversine_km(
                loc.latitude,
                loc.longitude,
                leader_location.latitude,
                leader_location.longitude,
            )

        entries.append(
            RiderLocationEntry(
                rider_id=rider.id,
                rider_name=rider.name,
                status=rider.status,
                location=(
                    GeoPointSchema(latitude=loc.latitude, longitude=loc.longitude) if loc else None
                ),
                speed_kmh=loc.speed_kmh if loc else None,
                recorded_at=loc.recorded_at if loc else None,
                distance_from_leader_km=distance_from_leader,
            )
        )

    return GroupLocationsResponse(ride_id=ride_id, riders=entries, generated_at=utc_now())

