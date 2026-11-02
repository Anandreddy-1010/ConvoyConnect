"""
app/models/ride.py
-------------------
Internal storage representation of a Ride.

NOTE ON ARCHITECTURE:
This is deliberately a plain `dataclass`, not a Pydantic schema and not
a SQLAlchemy model. It represents "the shape of a ride as stored",
independent of both the API contract (see app/schemas/ride.py) and the
eventual storage engine.

  - Today:  held in a Python dict inside InMemoryRideRepository.
  - Later:  this class's fields map directly onto a SQLAlchemy
            declarative model (Postgres) or a Firestore document
            schema (Firebase) — see app/repositories/README.md.

Keeping "storage model" and "API schema" separate (even though they
look similar right now) means the API response shape can evolve
independently of what's persisted, and vice versa.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class GeoPoint:
    """A plain latitude/longitude pair. No validation beyond typing —
    validation belongs in the API schema layer (Pydantic)."""

    latitude: Optional[float] = None
    longitude: Optional[float] = None


@dataclass
class RideRecord:
    id: str
    name: str
    invite_code: str
    created_by_rider_id: str
    start_location_name: str
    destination_location_name: str
    start_point: GeoPoint = field(default_factory=GeoPoint)
    destination_point: GeoPoint = field(default_factory=GeoPoint)
    status: str = "active"  # mirrors models.enums.RideStatus.value
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
