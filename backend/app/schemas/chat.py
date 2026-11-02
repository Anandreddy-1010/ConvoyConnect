"""
app/schemas/chat.py
--------------------
Pydantic request/response models for group chat messages.

NOTE: Message text is stored and returned as-is. No NLP processing
(intent classification, entity extraction, sentiment, etc.) happens in
Phase 2 — see app/nlp/README.md for the Phase 3 plan.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict

from app.models.enums import ChatMessageType


class ChatMessageCreateRequest(BaseModel):
    """Body for POST /api/v1/rides/{ride_id}/chat."""

    rider_id: str = Field(..., description="ID of the rider sending the message.")
    text: str = Field(..., min_length=1, max_length=2000)


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    ride_id: str
    rider_id: Optional[str] = None
    rider_name: Optional[str] = Field(
        default=None, description="Denormalized sender name for convenient display; null for system messages."
    )
    text: str
    message_type: ChatMessageType
    created_at: datetime
