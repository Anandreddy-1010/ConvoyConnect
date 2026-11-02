from typing import List

from app.models.sos import SOSAlert
from app.repositories.base import RideRepository, RiderRepository
from app.repositories.sqlite.sos_repository import SQLiteSOSRepository
from app.services.rider_service import RiderService
from app.utils.ids import generate_id


class SOSService:

    def __init__(
        self,
        ride_repo: RideRepository,
        rider_repo: RiderRepository,
        sos_repo=None,
    ):
        self._ride_repo = ride_repo
        self._rider_repo = rider_repo
        self._rider_service = RiderService(rider_repo, ride_repo)
        self._sos_repo = sos_repo or SQLiteSOSRepository()

    def create_alert(
        self,
        ride_id: str,
        rider_id: str,
        message: str,
        latitude: float = None,
        longitude: float = None,
    ) -> SOSAlert:

        rider = self._rider_service.get_rider_in_ride(ride_id, rider_id)

        if (latitude is None) != (longitude is None):
            raise ValueError("Latitude and longitude must be provided together.")

        if latitude is not None and not (-90 <= latitude <= 90):
            raise ValueError("Latitude must be between -90 and 90.")

        if longitude is not None and not (-180 <= longitude <= 180):
            raise ValueError("Longitude must be between -180 and 180.")

        alert = SOSAlert(
            id=generate_id("sos"),
            ride_id=ride_id,
            rider_id=rider_id,
            rider_name=rider.name,
            message=message,
            latitude=latitude,
            longitude=longitude,
        )

        return self._sos_repo.create(alert)

    def list_alerts(self, ride_id: str) -> List[SOSAlert]:

        if self._ride_repo.get_by_id(ride_id) is None:
            from app.core.exceptions import RideNotFoundError
            raise RideNotFoundError(ride_id)

        return [
            alert
            for alert in self._sos_repo.list_by_ride(ride_id)
            if alert.active
        ]

    def resolve_alert(self, ride_id: str, alert_id: str) -> SOSAlert:

        alert = self._sos_repo.get_by_id(alert_id)

        if alert is None or alert.ride_id != ride_id:
            raise KeyError("SOS alert not found.")

        alert.active = False
        return self._sos_repo.update(alert)
