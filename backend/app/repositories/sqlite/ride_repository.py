from datetime import datetime

from app.models.ride import RideRecord, GeoPoint
from app.repositories.base import RideRepository
from app.repositories.sqlite.database import get_connection


class SQLiteRideRepository(RideRepository):

    def create(self, ride: RideRecord) -> RideRecord:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO rides (
                    id, name, invite_code, created_by_rider_id,
                    start_location_name, destination_location_name,
                    start_latitude, start_longitude,
                    destination_latitude, destination_longitude,
                    status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ride.id,
                    ride.name,
                    ride.invite_code,
                    ride.created_by_rider_id,
                    ride.start_location_name,
                    ride.destination_location_name,
                    ride.start_point.latitude,
                    ride.start_point.longitude,
                    ride.destination_point.latitude,
                    ride.destination_point.longitude,
                    ride.status,
                    ride.created_at.isoformat(),
                ),
            )
        return ride

    def _to_record(self, row):
        if row is None:
            return None

        return RideRecord(
            id=row["id"],
            name=row["name"],
            invite_code=row["invite_code"],
            created_by_rider_id=row["created_by_rider_id"],
            start_location_name=row["start_location_name"],
            destination_location_name=row["destination_location_name"],
            start_point=GeoPoint(
                latitude=row["start_latitude"],
                longitude=row["start_longitude"],
            ),
            destination_point=GeoPoint(
                latitude=row["destination_latitude"],
                longitude=row["destination_longitude"],
            ),
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def get_by_id(self, ride_id: str):
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM rides WHERE id = ?", (ride_id,)
            ).fetchone()
        return self._to_record(row)

    def get_by_invite_code(self, invite_code: str):
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM rides WHERE invite_code = ?",
                (invite_code,),
            ).fetchone()
        return self._to_record(row)

    def list_all(self):
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM rides ORDER BY created_at"
            ).fetchall()
        return [self._to_record(row) for row in rows]
