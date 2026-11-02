"""
app/utils/time_utils.py
-------------------------
Timestamp helpers. Centralized so every module produces
timezone-aware UTC timestamps consistently.
"""

from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
