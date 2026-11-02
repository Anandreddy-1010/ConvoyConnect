
"""
app/api/deps.py
------------------
FastAPI dependency-injection providers.
"""

from functools import lru_cache

from app.repositories.factory import (
    chat_repository,
    location_repository,
    ride_repository,
    rider_repository,
)
from app.services.chat_service import ChatService
from app.services.location_service import LocationService
from app.services.ride_service import RideService
from app.services.rider_service import RiderService
from app.services.sos_service import SOSService


def get_ride_service() -> RideService:
    return RideService(
        ride_repo=ride_repository,
        rider_repo=rider_repository,
    )


def get_rider_service() -> RiderService:
    return RiderService(
        rider_repo=rider_repository,
        ride_repo=ride_repository,
    )


def get_location_service() -> LocationService:
    return LocationService(
        location_repo=location_repository,
        rider_repo=rider_repository,
        ride_repo=ride_repository,
    )


def get_chat_service() -> ChatService:
    return ChatService(
        chat_repo=chat_repository,
        rider_repo=rider_repository,
        ride_repo=ride_repository,
    )


@lru_cache(maxsize=1)
def get_sos_service() -> SOSService:
    return SOSService(
        ride_repo=ride_repository,
        rider_repo=rider_repository,
    )
from app.services.push_service import PushService


@lru_cache(maxsize=1)
def get_push_service() -> PushService:
    return PushService()
