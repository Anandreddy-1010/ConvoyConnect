"""
app/models/rider.py
--------------------
Internal storage representation of a Rider (a person participating in
a specific ride). See app/models/ride.py for notes on why this is a
plain dataclass rather than a Pydantic schema or ORM model.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class RiderRecord:
    id: str
    ride_id: str
    name: str
    role: str = "member"        # mirrors models.enums.RiderRole.value
    status: str = "on_track"    # mirrors models.enums.RiderStatus.value
    phone: Optional[str] = None
    bike_model: Optional[str] = None
    joined_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
