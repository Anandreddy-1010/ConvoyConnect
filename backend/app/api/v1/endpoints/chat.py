"""
app/api/v1/endpoints/chat.py
--------------------------------
Group chat endpoints, nested under a ride:

  POST /api/v1/rides/{ride_id}/chat   send a message
  GET  /api/v1/rides/{ride_id}/chat   list messages (bonus endpoint —
                                        not in the original spec, but
                                        needed to actually verify sent
                                        messages via Swagger/tests)

NOTE: No NLP is applied to message text. Messages are stored and
returned exactly as submitted — see app/nlp/README.md for the planned
Phase 3 intent classification / entity extraction pipeline.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_chat_service
from app.core.exceptions import RideNotFoundError, RiderNotFoundError
from app.repositories.factory import rider_repository
from app.schemas.chat import ChatMessageCreateRequest, ChatMessageResponse
from app.services.chat_service import ChatService
from app.services.mappers import chat_message_to_response

router = APIRouter()


@router.post(
    "/{ride_id}/chat",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send a group chat message",
)
def send_message(
    ride_id: str,
    request: ChatMessageCreateRequest,
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatMessageResponse:
    try:
        message = chat_service.send_message(ride_id, request)
    except (RideNotFoundError, RiderNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return chat_message_to_response(message, rider_repository)


@router.get(
    "/{ride_id}/chat",
    response_model=List[ChatMessageResponse],
    summary="List group chat messages for a ride",
)
def list_messages(
    ride_id: str,
    chat_service: ChatService = Depends(get_chat_service),
) -> List[ChatMessageResponse]:
    try:
        messages = chat_service.list_messages(ride_id)
    except RideNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return [chat_message_to_response(m, rider_repository) for m in messages]
