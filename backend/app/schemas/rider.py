"""
app/schemas/rider.py
---------------------
Pydantic request/response models for the Rider resource.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict

from app.models.enums import RiderRole, RiderStatus
from app.schemas.location import LocationUpdateResponse


class RiderAddRequest(BaseModel):
    """Body for POST /api/v1/rides/{ride_id}/riders.

    Distinct from RideJoinRequest: this endpoint adds a rider directly
    to a *known* ride_id (e.g. a ride leader adding someone manually,
    or a test/seed script), without requiring an invite code lookup.
    """

    name: str = Field(..., min_length=1, examples=["Sofia Kim"])
    role: RiderRole = RiderRole.MEMBER
    phone: Optional[str] = None
    bike_model: Optional[str] = None


class RiderStatusUpdateRequest(BaseModel):
    """Body for PATCH /api/v1/rides/{ride_id}/riders/{rider_id}/status.

    NOTE: In Phase 2, status is set explicitly by whoever calls this
    endpoint (a rider's app, or a test script). It is NOT yet inferred
    automatically — automatic status inference (via GPS trajectory +
    group-state detection) is planned for app/geospatial and
    app/group_ai in a later phase.
    """

    status: RiderStatus


class RiderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    ride_id: str
    name: str
    role: RiderRole
    status: RiderStatus
    phone: Optional[str] = None
    bike_model: Optional[str] = None
    joined_at: datetime
    last_location: Optional[LocationUpdateResponse] = Field(
        default=None,
        description="Most recent GPS update for this rider, if any has been submitted.",
    )
