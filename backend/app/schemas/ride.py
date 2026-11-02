"""
app/schemas/ride.py
--------------------
Pydantic request/response models for the Ride resource.

These define the *public API contract* — what a client sends and
receives over HTTP. They are intentionally kept separate from
app/models/ride.py (the internal storage representation).
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict

from app.models.enums import RideStatus
from app.schemas.common import GeoPointSchema


class RideCreateRequest(BaseModel):
    """Body for POST /api/v1/rides — creates a ride and its leader."""

    ride_name: str = Field(..., min_length=1, max_length=120, examples=["PNW Coastal Run"])
    start_location_name: str = Field(..., min_length=1, examples=["Seattle, WA"])
    destination_location_name: str = Field(..., min_length=1, examples=["Astoria, OR"])
    start_point: Optional[GeoPointSchema] = Field(
        default=None, description="Optional known coordinates for the start location."
    )
    destination_point: Optional[GeoPointSchema] = Field(
        default=None, description="Optional known coordinates for the destination."
    )
    leader_name: str = Field(..., min_length=1, examples=["You"])
    leader_phone: Optional[str] = None
    leader_bike_model: Optional[str] = None


class RideJoinRequest(BaseModel):
    """Body for POST /api/v1/rides/join — an additional rider joins an
    existing ride using its invite code."""

    invite_code: str = Field(..., min_length=1, examples=["CONVOY-7F2K"])
    rider_name: str = Field(..., min_length=1, examples=["Priya Nair"])
    rider_phone: Optional[str] = None
    bike_model: Optional[str] = None


class RideResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    invite_code: str
    status: RideStatus
    start_location_name: str
    destination_location_name: str
    start_point: Optional[GeoPointSchema] = None
    destination_point: Optional[GeoPointSchema] = None
    created_by_rider_id: str
    created_at: datetime
    rider_count: int = Field(..., description="Number of riders currently on this ride.")
