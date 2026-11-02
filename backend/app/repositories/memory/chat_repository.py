"""
app/repositories/memory/chat_repository.py
---------------------------------------------
In-memory implementation of ChatRepository. Messages are stored in a
single list and filtered by ride_id on read; fine for prototype-scale
data, not intended to scale — a real database would index by ride_id.
"""

from typing import Dict, List

from app.models.chat import ChatMessageRecord
from app.repositories.base import ChatRepository


class InMemoryChatRepository(ChatRepository):
    def __init__(self) -> None:
        self._messages_by_ride: Dict[str, List[ChatMessageRecord]] = {}

    def create(self, message: ChatMessageRecord) -> ChatMessageRecord:
        self._messages_by_ride.setdefault(message.ride_id, []).append(message)
        return message

    def list_by_ride(self, ride_id: str) -> List[ChatMessageRecord]:
        return list(self._messages_by_ride.get(ride_id, []))
