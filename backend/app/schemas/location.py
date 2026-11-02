"""
app/schemas/location.py
------------------------
Pydantic request/response models for GPS location updates.

DISCLAIMER: These endpoints accept and return whatever coordinates the
caller submits. There is no live device/GPS integration, background
polling, or streaming in Phase 2 â€” a client must explicitly call
PUT /rides/{ride_id}/riders/{rider_id}/location to record a position.
Real-time tracking is a Phase 3+ goal (see app/geospatial/README.md).
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict

from app.models.enums import RiderStatus
from app.schemas.common import GeoPointSchema


class LocationUpdateRequest(BaseModel):
    """Body for PUT /api/v1/rides/{ride_id}/riders/{rider_id}/location."""

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    speed_kmh: Optional[float] = Field(default=None, ge=0, description="Self-reported speed, if available.")
    heading_deg: Optional[float] = Field(default=None, ge=0, lt=360, description="Compass heading, if available.")


class LocationUpdateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rider_id: str
    latitude: float
    longitude: float
    speed_kmh: Optional[float] = None
    heading_deg: Optional[float] = None
    recorded_at: datetime


class RiderLocationEntry(BaseModel):
    """One rider's latest known position, used inside GroupLocationsResponse."""

    rider_id: str
    rider_name: str
    status: RiderStatus
    location: Optional[GeoPointSchema] = None
    speed_kmh: Optional[float] = None
    recorded_at: Optional[datetime] = None
    distance_from_leader_km: Optional[float] = None


class GroupLocationsResponse(BaseModel):
    """Response for GET /api/v1/rides/{ride_id}/locations.

    Returns the latest known position for every rider in the ride who
    has submitted at least one location update. Riders with no
    location yet are included with `location: null` so the frontend
    can distinguish "no data yet" from "at coordinate 0,0".
    """

    ride_id: str
    riders: List[RiderLocationEntry]
    generated_at: datetime

