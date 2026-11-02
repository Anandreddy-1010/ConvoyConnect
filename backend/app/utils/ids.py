"""
app/utils/ids.py
------------------
ID and invite-code generation helpers, kept in one place so the
format can change later (e.g. to database-generated UUIDs/serials)
without touching every service that creates a record.
"""

import random
import string
import uuid


def generate_id(prefix: str) -> str:
    """e.g. generate_id('ride') -> 'ride_3f9a2c1b8e4d4a2c'"""
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def generate_invite_code() -> str:
    """e.g. 'CONVOY-7F2K' — matches the format used in the frontend mock."""
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"CONVOY-{suffix}"
