from datetime import datetime

from app.models.rider import RiderRecord
from app.repositories.base import RiderRepository
from app.repositories.sqlite.database import get_connection


class SQLiteRiderRepository(RiderRepository):

    def create(self, rider: RiderRecord) -> RiderRecord:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO riders (
                    id, ride_id, name, role, status,
                    phone, bike_model, joined_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rider.id,
                    rider.ride_id,
                    rider.name,
                    rider.role,
                    rider.status,
                    rider.phone,
                    rider.bike_model,
                    rider.joined_at.isoformat(),
                ),
            )
        return rider

    def _to_record(self, row):
        if row is None:
            return None

        return RiderRecord(
            id=row["id"],
            ride_id=row["ride_id"],
            name=row["name"],
            role=row["role"],
            status=row["status"],
            phone=row["phone"],
            bike_model=row["bike_model"],
            joined_at=datetime.fromisoformat(row["joined_at"]),
        )

    def get_by_id(self, rider_id: str):
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM riders WHERE id = ?", (rider_id,)
            ).fetchone()
        return self._to_record(row)

    def list_by_ride(self, ride_id: str):
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM riders WHERE ride_id = ? ORDER BY joined_at",
                (ride_id,),
            ).fetchall()
        return [self._to_record(row) for row in rows]

    def update(self, rider: RiderRecord) -> RiderRecord:
        with get_connection() as connection:
            cursor = connection.execute(
                """
                UPDATE riders
                SET ride_id = ?, name = ?, role = ?, status = ?,
                    phone = ?, bike_model = ?, joined_at = ?
                WHERE id = ?
                """,
                (
                    rider.ride_id,
                    rider.name,
                    rider.role,
                    rider.status,
                    rider.phone,
                    rider.bike_model,
                    rider.joined_at.isoformat(),
                    rider.id,
                ),
            )

            if cursor.rowcount == 0:
                raise ValueError(f"Rider '{rider.id}' does not exist.")

        return rider

    def count_for_ride(self, ride_id: str) -> int:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM riders WHERE ride_id = ?",
                (ride_id,),
            ).fetchone()
        return row["total"]
