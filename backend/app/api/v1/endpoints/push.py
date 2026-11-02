from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_push_service
from app.services.push_service import PushService

router = APIRouter()


class PushSubscribeRequest(BaseModel):
    ride_id: str = Field(min_length=1)
    rider_id: str = Field(min_length=1)
    subscription: dict


@router.post("/subscribe", status_code=201)
def subscribe(
    request: PushSubscribeRequest,
    service: PushService = Depends(get_push_service),
):
    try:
        service.save_subscription(
            ride_id=request.ride_id,
            rider_id=request.rider_id,
            subscription=request.subscription,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {"message": "Push subscription saved successfully."}
