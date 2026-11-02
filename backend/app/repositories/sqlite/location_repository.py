from datetime import datetime

from app.models.location import LocationRecord
from app.repositories.base import LocationRepository
from app.repositories.sqlite.database import get_connection


class SQLiteLocationRepository(LocationRepository):

    def upsert(self, location: LocationRecord) -> LocationRecord:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO locations (
                    rider_id, ride_id, latitude, longitude,
                    speed_kmh, heading_deg, recorded_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(rider_id) DO UPDATE SET
                    ride_id = excluded.ride_id,
                    latitude = excluded.latitude,
                    longitude = excluded.longitude,
                    speed_kmh = excluded.speed_kmh,
                    heading_deg = excluded.heading_deg,
                    recorded_at = excluded.recorded_at
                """,
                (
                    location.rider_id,
                    location.ride_id,
                    location.latitude,
                    location.longitude,
                    location.speed_kmh,
                    location.heading_deg,
                    location.recorded_at.isoformat(),
                ),
            )
        return location

    def _to_record(self, row):
        if row is None:
            return None

        return LocationRecord(
            rider_id=row["rider_id"],
            ride_id=row["ride_id"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            speed_kmh=row["speed_kmh"],
            heading_deg=row["heading_deg"],
            recorded_at=datetime.fromisoformat(row["recorded_at"]),
        )

    def get_latest_for_rider(self, rider_id: str):
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM locations WHERE rider_id = ?",
                (rider_id,),
            ).fetchone()

        return self._to_record(row)

    def get_latest_for_ride(self, ride_id: str):
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM locations WHERE ride_id = ?",
                (ride_id,),
            ).fetchall()

        return {
            row["rider_id"]: self._to_record(row)
            for row in rows
        }
