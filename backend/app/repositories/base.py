"""
app/repositories/base.py
-------------------------
Abstract repository interfaces.

WHY THIS FILE EXISTS:
The service layer (app/services/*) depends only on these interfaces,
never on a concrete storage implementation. That means swapping the
in-memory store for PostgreSQL (via SQLAlchemy) or Firebase (via the
Firestore SDK) later is a matter of writing a new class that satisfies
the same interface — no changes needed in services or API routes.

    app/repositories/
        base.py              <- interfaces defined here
        memory/               <- Phase 2: in-memory implementations
        postgres/              <- Phase 3+: SQLAlchemy implementations (not yet built)
        firebase/               <- Phase 3+: Firestore implementations (not yet built)

Each interface below is deliberately minimal — just what Phase 2's
endpoints need. Extend with pagination, filtering, etc. as needed.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from app.models.chat import ChatMessageRecord
from app.models.location import LocationRecord
from app.models.ride import RideRecord
from app.models.rider import RiderRecord


class RideRepository(ABC):
    @abstractmethod
    def create(self, ride: RideRecord) -> RideRecord: ...

    @abstractmethod
    def get_by_id(self, ride_id: str) -> Optional[RideRecord]: ...

    @abstractmethod
    def get_by_invite_code(self, invite_code: str) -> Optional[RideRecord]: ...

    @abstractmethod
    def list_all(self) -> List[RideRecord]: ...


class RiderRepository(ABC):
    @abstractmethod
    def create(self, rider: RiderRecord) -> RiderRecord: ...

    @abstractmethod
    def get_by_id(self, rider_id: str) -> Optional[RiderRecord]: ...

    @abstractmethod
    def list_by_ride(self, ride_id: str) -> List[RiderRecord]: ...

    @abstractmethod
    def update(self, rider: RiderRecord) -> RiderRecord: ...

    @abstractmethod
    def count_for_ride(self, ride_id: str) -> int: ...


class LocationRepository(ABC):
    @abstractmethod
    def upsert(self, location: LocationRecord) -> LocationRecord:
        """Store a new location update. Phase 2 only keeps the latest
        per rider; a later phase may retain full trajectory history."""
        ...

    @abstractmethod
    def get_latest_for_rider(self, rider_id: str) -> Optional[LocationRecord]: ...

    @abstractmethod
    def get_latest_for_ride(self, ride_id: str) -> Dict[str, LocationRecord]:
        """Returns {rider_id: LocationRecord} for every rider in the
        ride that has at least one recorded location."""
        ...


class ChatRepository(ABC):
    @abstractmethod
    def create(self, message: ChatMessageRecord) -> ChatMessageRecord: ...

    @abstractmethod
    def list_by_ride(self, ride_id: str) -> List[ChatMessageRecord]: ...
