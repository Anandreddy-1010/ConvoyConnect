from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import get_push_service, get_sos_service
from app.core.exceptions import (
    RideNotFoundError,
    RiderNotFoundError,
    RiderNotInRideError,
)
from app.models.sos import SOSAlert
from app.services.sos_service import SOSService
from app.services.push_service import PushService

router = APIRouter()


class SOSCreateRequest(BaseModel):
    rider_id: str
    message: str = Field(
        default="Emergency! I need help.",
        min_length=1,
        max_length=500,
    )
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)


class SOSResponse(BaseModel):
    id: str
    ride_id: str
    rider_id: str
    rider_name: str
    message: str
    latitude: Optional[float]
    longitude: Optional[float]
    active: bool
    created_at: datetime


def to_response(alert: SOSAlert) -> SOSResponse:
    return SOSResponse(**vars(alert))


@router.post(
    "/{ride_id}",
    response_model=SOSResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_sos(
    ride_id: str,
    request: SOSCreateRequest,
    service: SOSService = Depends(get_sos_service),
    push_service: PushService = Depends(get_push_service),
):
    try:
        alert = service.create_alert(
            ride_id=ride_id,
            rider_id=request.rider_id,
            message=request.message,
            latitude=request.latitude,
            longitude=request.longitude,
        )
    except (
        RideNotFoundError,
        RiderNotFoundError,
        RiderNotInRideError,
    ) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Push delivery must not prevent the SOS alert from being created.
    try:
        push_service.notify_other_riders(
            ride_id=ride_id,
            sender_id=request.rider_id,
            alert=alert,
        )
    except Exception as exc:
        print(f"SOS push notification failed: {exc}")

    return to_response(alert)


@router.get("/{ride_id}", response_model=List[SOSResponse])
def list_sos(
    ride_id: str,
    service: SOSService = Depends(get_sos_service),
):
    try:
        return [
            to_response(alert)
            for alert in service.list_alerts(ride_id)
        ]
    except RideNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch(
    "/{ride_id}/{alert_id}/resolve",
    response_model=SOSResponse,
)
def resolve_sos(
    ride_id: str,
    alert_id: str,
    service: SOSService = Depends(get_sos_service),
):
    try:
        return to_response(service.resolve_alert(ride_id, alert_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc