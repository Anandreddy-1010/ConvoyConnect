from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class SOSAlert:
    id: str
    ride_id: str
    rider_id: str
    rider_name: str
    message: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    active: bool = True
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )