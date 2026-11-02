"""
Optional startup seed data.
Demo data is inserted only once.
"""

from app.models.chat import ChatMessageRecord
from app.models.enums import ChatMessageType, RiderRole, RiderStatus
from app.models.location import LocationRecord
from app.models.ride import GeoPoint, RideRecord
from app.models.rider import RiderRecord
from app.repositories.base import (
    ChatRepository,
    LocationRepository,
    RideRepository,
    RiderRepository,
)


def seed_demo_data(
    ride_repo: RideRepository,
    rider_repo: RiderRepository,
    location_repo: LocationRepository,
    chat_repo: ChatRepository,
) -> None:

    ride = RideRecord(
        id="ride_8842",
        name="PNW Coastal Run",
        invite_code="CONVOY-7F2K",
        created_by_rider_id="u1",
        start_location_name="Seattle, WA",
        destination_location_name="Astoria, OR",
        start_point=GeoPoint(latitude=47.6062, longitude=-122.3321),
        destination_point=GeoPoint(latitude=46.1879, longitude=-123.8313),
    )

    # Prevent duplicate demo data on backend restart.
    if (
        ride_repo.get_by_id(ride.id)
        or ride_repo.get_by_invite_code(ride.invite_code)
    ):
        print("Demo data already exists. Skipping seed.")
        return

    ride_repo.create(ride)

    riders = [
        RiderRecord(id="u1", ride_id=ride.id, name="You", role=RiderRole.LEADER.value,
                    status=RiderStatus.ON_TRACK.value, phone="+1 (206) 555-0142", bike_model="Triumph Tiger 900"),
        RiderRecord(id="u2", ride_id=ride.id, name="Marcus Bell", role=RiderRole.MEMBER.value,
                    status=RiderStatus.ON_TRACK.value, phone="+1 (206) 555-0198", bike_model="Harley-Davidson Pan America"),
        RiderRecord(id="u3", ride_id=ride.id, name="Priya Nair", role=RiderRole.MEMBER.value,
                    status=RiderStatus.DELAYED.value, phone="+1 (206) 555-0110", bike_model="Kawasaki Versys 650"),
        RiderRecord(id="u4", ride_id=ride.id, name="Diego Alvarez", role=RiderRole.MEMBER.value,
                    status=RiderStatus.SEPARATED.value, phone="+1 (206) 555-0187", bike_model="Honda Africa Twin"),
        RiderRecord(id="u5", ride_id=ride.id, name="Sofia Kim", role=RiderRole.MEMBER.value,
                    status=RiderStatus.STOPPED.value, phone="+1 (206) 555-0173", bike_model="Yamaha Ténéré 700"),
    ]

    for rider in riders:
        rider_repo.create(rider)

    locations = [
        LocationRecord(rider_id="u1", ride_id=ride.id, latitude=46.85, longitude=-123.55, speed_kmh=93.34),
        LocationRecord(rider_id="u2", ride_id=ride.id, latitude=46.84, longitude=-123.53, speed_kmh=90.12),
        LocationRecord(rider_id="u3", ride_id=ride.id, latitude=46.90, longitude=-123.40, speed_kmh=65.98),
        LocationRecord(rider_id="u4", ride_id=ride.id, latitude=47.05, longitude=-123.10, speed_kmh=0),
        LocationRecord(rider_id="u5", ride_id=ride.id, latitude=46.88, longitude=-123.47, speed_kmh=0),
    ]

    for location in locations:
        location_repo.upsert(location)

    messages = [
        ChatMessageRecord(id="msg_1", ride_id=ride.id, rider_id="u2",
                          text="Fuel stop in 10 miles, gas is getting low on mine."),
        ChatMessageRecord(id="msg_2", ride_id=ride.id, rider_id="u1",
                          text="Copy that, pulling into the Chevron up ahead."),
        ChatMessageRecord(id="msg_3", ride_id=ride.id, rider_id=None,
                          text="Priya Nair has fallen behind the group.",
                          message_type=ChatMessageType.SYSTEM.value),
        ChatMessageRecord(id="msg_4", ride_id=ride.id, rider_id="u3",
                          text="Sorry, hit a slow tractor on the 2-lane. Catching up."),
    ]

    for message in messages:
        chat_repo.create(message)

    print("Demo data created successfully.")
