"""
app/core/exceptions.py
-----------------------
Domain-level exceptions raised by the service layer.

Keeping these independent of FastAPI/HTTP means the service layer stays
usable outside of a web request (e.g. from a background job, a CLI
script, or a future websocket handler). The API layer (app/api/...) is
responsible for catching these and translating them into the correct
HTTP status codes and response bodies.
"""


class ConvoyConnectError(Exception):
    """Base class for all domain errors in this application."""


class RideNotFoundError(ConvoyConnectError):
    """Raised when a ride_id does not match any known ride."""

    def __init__(self, ride_id: str):
        self.ride_id = ride_id
        super().__init__(f"Ride '{ride_id}' was not found.")


class InvalidInviteCodeError(ConvoyConnectError):
    """Raised when a join request uses an invite code that doesn't exist."""

    def __init__(self, invite_code: str):
        self.invite_code = invite_code
        super().__init__(f"Invite code '{invite_code}' is not valid.")


class RiderNotFoundError(ConvoyConnectError):
    """Raised when a rider_id does not match any known rider."""

    def __init__(self, rider_id: str):
        self.rider_id = rider_id
        super().__init__(f"Rider '{rider_id}' was not found.")


class RiderNotInRideError(ConvoyConnectError):
    """Raised when a rider exists, but not within the specified ride."""

    def __init__(self, rider_id: str, ride_id: str):
        self.rider_id = rider_id
        self.ride_id = ride_id
        super().__init__(f"Rider '{rider_id}' is not part of ride '{ride_id}'.")
