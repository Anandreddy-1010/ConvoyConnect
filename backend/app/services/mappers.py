"""
app/services/mappers.py
--------------------------
Functions that convert internal storage records (app/models/*) into
API response schemas (app/schemas/*).

Kept separate from the schemas themselves and from the repositories so
that neither has to know about the other — this module is the only
place that translates between the two shapes.
"""

from typing import Optional

from app.models.chat import ChatMessageRecord
from app.models.location import LocationRecord
from app.models.ride import RideRecord
from app.models.rider import RiderRecord
from app.repositories.base import RiderRepository
from app.schemas.chat import ChatMessageResponse
from app.schemas.common import GeoPointSchema
from app.schemas.location import LocationUpdateResponse
from app.schemas.ride import RideResponse
from app.schemas.rider import RiderResponse


def ride_to_response(ride: RideRecord, rider_count: int) -> RideResponse:
    return RideResponse(
        id=ride.id,
        name=ride.name,
        invite_code=ride.invite_code,
        status=ride.status,
        start_location_name=ride.start_location_name,
        destination_location_name=ride.destination_location_name,
        start_point=(
            GeoPointSchema(latitude=ride.start_point.latitude, longitude=ride.start_point.longitude)
            if ride.start_point.latitude is not None and ride.start_point.longitude is not None
            else None
        ),
        destination_point=(
            GeoPointSchema(
                latitude=ride.destination_point.latitude, longitude=ride.destination_point.longitude
            )
            if ride.destination_point.latitude is not None and ride.destination_point.longitude is not None
            else None
        ),
        created_by_rider_id=ride.created_by_rider_id,
        created_at=ride.created_at,
        rider_count=rider_count,
    )


def location_to_response(location: Optional[LocationRecord]) -> Optional[LocationUpdateResponse]:
    if location is None:
        return None
    return LocationUpdateResponse(
        rider_id=location.rider_id,
        latitude=location.latitude,
        longitude=location.longitude,
        speed_kmh=location.speed_kmh,
        heading_deg=location.heading_deg,
        recorded_at=location.recorded_at,
    )


def rider_to_response(rider: RiderRecord, latest_location: Optional[LocationRecord] = None) -> RiderResponse:
    return RiderResponse(
        id=rider.id,
        ride_id=rider.ride_id,
        name=rider.name,
        role=rider.role,
        status=rider.status,
        phone=rider.phone,
        bike_model=rider.bike_model,
        joined_at=rider.joined_at,
        last_location=location_to_response(latest_location),
    )


def chat_message_to_response(
    message: ChatMessageRecord, rider_repo: RiderRepository
) -> ChatMessageResponse:
    rider_name: Optional[str] = None
    if message.rider_id:
        sender = rider_repo.get_by_id(message.rider_id)
        rider_name = sender.name if sender else None

    return ChatMessageResponse(
        id=message.id,
        ride_id=message.ride_id,
        rider_id=message.rider_id,
        rider_name=rider_name,
        text=message.text,
        message_type=message.message_type,
        created_at=message.created_at,
    )
