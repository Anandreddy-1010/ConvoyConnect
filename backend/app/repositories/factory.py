"""
Repository factory supporting memory and SQLite storage.
"""

from app.core.config import get_settings
from app.repositories.base import (
    ChatRepository,
    LocationRepository,
    RideRepository,
    RiderRepository,
)
from app.repositories.memory.chat_repository import InMemoryChatRepository
from app.repositories.memory.location_repository import InMemoryLocationRepository
from app.repositories.memory.ride_repository import InMemoryRideRepository
from app.repositories.memory.rider_repository import InMemoryRiderRepository

_settings = get_settings()

if _settings.DATA_BACKEND == "sqlite":
    from app.repositories.sqlite.database import initialize_database
    from app.repositories.sqlite.chat_repository import SQLiteChatRepository
    from app.repositories.sqlite.location_repository import SQLiteLocationRepository
    from app.repositories.sqlite.ride_repository import SQLiteRideRepository
    from app.repositories.sqlite.rider_repository import SQLiteRiderRepository

    initialize_database()


def _build_ride_repository() -> RideRepository:
    if _settings.DATA_BACKEND == "memory":
        return InMemoryRideRepository()
    if _settings.DATA_BACKEND == "sqlite":
        return SQLiteRideRepository()
    raise NotImplementedError(
        f"Unsupported DATA_BACKEND: {_settings.DATA_BACKEND}"
    )


def _build_rider_repository() -> RiderRepository:
    if _settings.DATA_BACKEND == "memory":
        return InMemoryRiderRepository()
    if _settings.DATA_BACKEND == "sqlite":
        return SQLiteRiderRepository()
    raise NotImplementedError(
        f"Unsupported DATA_BACKEND: {_settings.DATA_BACKEND}"
    )


def _build_location_repository() -> LocationRepository:
    if _settings.DATA_BACKEND == "memory":
        return InMemoryLocationRepository()
    if _settings.DATA_BACKEND == "sqlite":
        return SQLiteLocationRepository()
    raise NotImplementedError(
        f"Unsupported DATA_BACKEND: {_settings.DATA_BACKEND}"
    )


def _build_chat_repository() -> ChatRepository:
    if _settings.DATA_BACKEND == "memory":
        return InMemoryChatRepository()
    if _settings.DATA_BACKEND == "sqlite":
        return SQLiteChatRepository()
    raise NotImplementedError(
        f"Unsupported DATA_BACKEND: {_settings.DATA_BACKEND}"
    )


ride_repository: RideRepository = _build_ride_repository()
rider_repository: RiderRepository = _build_rider_repository()
location_repository: LocationRepository = _build_location_repository()
chat_repository: ChatRepository = _build_chat_repository()
