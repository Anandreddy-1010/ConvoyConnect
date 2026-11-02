"""
app/schemas/common.py
----------------------
Small, reusable Pydantic pieces shared across multiple schema files.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class GeoPointSchema(BaseModel):
    """A latitude/longitude pair as exposed over the API."""

    latitude: float = Field(..., ge=-90, le=90, description="Latitude in decimal degrees")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude in decimal degrees")


class HealthResponse(BaseModel):
    status: str = Field(..., examples=["ok"])
    service: str
    version: str
    time: datetime


class ErrorResponse(BaseModel):
    """Standard error body returned by HTTPException handlers."""

    detail: str
