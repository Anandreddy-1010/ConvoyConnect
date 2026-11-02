"""
app/services/chat_service.py
-------------------------------
Business logic for group chat messages.

NOTE: No NLP is applied to message text in Phase 2 (no intent
classification, no entity extraction, no auto-generated responses).
Messages are stored and returned verbatim. See app/nlp/README.md for
the Phase 3 plan.
"""

from typing import List

from app.core.exceptions import RideNotFoundError, RiderNotFoundError
from app.models.chat import ChatMessageRecord
from app.models.enums import ChatMessageType
from app.repositories.base import ChatRepository, RideRepository, RiderRepository
from app.schemas.chat import ChatMessageCreateRequest
from app.utils.ids import generate_id


class ChatService:
    def __init__(self, chat_repo: ChatRepository, rider_repo: RiderRepository, ride_repo: RideRepository):
        self._chat_repo = chat_repo
        self._rider_repo = rider_repo
        self._ride_repo = ride_repo

    def send_message(self, ride_id: str, request: ChatMessageCreateRequest) -> ChatMessageRecord:
        if self._ride_repo.get_by_id(ride_id) is None:
            raise RideNotFoundError(ride_id)

        sender = self._rider_repo.get_by_id(request.rider_id)
        if sender is None:
            raise RiderNotFoundError(request.rider_id)

        message = ChatMessageRecord(
            id=generate_id("msg"),
            ride_id=ride_id,
            rider_id=request.rider_id,
            text=request.text,
            message_type=ChatMessageType.TEXT.value,
        )
        return self._chat_repo.create(message)

    def list_messages(self, ride_id: str) -> List[ChatMessageRecord]:
        if self._ride_repo.get_by_id(ride_id) is None:
            raise RideNotFoundError(ride_id)
        return self._chat_repo.list_by_ride(ride_id)
