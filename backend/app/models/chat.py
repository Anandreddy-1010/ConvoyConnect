"""
app/models/chat.py
-------------------
Internal storage representation of a group chat message.

Phase 2 supports plain text messages sent by riders, plus "system"
messages (e.g. seeded demo alerts). There is no NLP processing of
message content yet — see app/nlp/README.md for the Phase 3 plan
(intent classification, entity extraction over chat text).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class ChatMessageRecord:
    id: str
    ride_id: str
    rider_id: Optional[str]   # None for system-generated messages
    text: str
    message_type: str = "text"  # mirrors models.enums.ChatMessageType.value
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
