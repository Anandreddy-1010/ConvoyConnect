"""
app/models/location.py
-----------------------
Internal storage representation of a single GPS location update.

IMPORTANT: This system does not yet receive real-time GPS. Phase 2
only stores whatever coordinates a client (or test script) submits via
the API — there is no device integration, background polling, or push
mechanism yet. See app/geospatial/README.md for the Phase 3 plan
(trajectory processing, haversine distance, separation detection).

Only the *latest* location per rider is kept in Phase 2
(InMemoryLocationRepository overwrites on each update). A later phase
may retain full trajectory history for delay-prediction models.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class LocationRecord:
    rider_id: str
    ride_id: str
    latitude: float
    longitude: float
    speed_kmh: Optional[float] = None
    heading_deg: Optional[float] = None
    recorded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
