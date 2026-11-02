"""
app/models/enums.py
--------------------
Shared enumerations for ride/rider domain state.

These are intentionally simple, hand-maintained states for Phase 2.
In a later phase, `RiderStatus` transitions (e.g. on_track -> delayed
-> separated) will be *computed* by app/geospatial and app/group_ai
instead of being set directly by the client. For now, the client (or
a test script) sets status explicitly via the API.
"""

from enum import Enum


class RiderStatus(str, Enum):
    ON_TRACK = "on_track"
    DELAYED = "delayed"
    SEPARATED = "separated"
    STOPPED = "stopped"
    SOS = "sos"


class RiderRole(str, Enum):
    LEADER = "leader"
    MEMBER = "member"


class RideStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ChatMessageType(str, Enum):
    TEXT = "text"
    SYSTEM = "system"
