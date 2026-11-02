from datetime import datetime

from app.models.sos import SOSAlert
from app.repositories.sqlite.database import get_connection


class SQLiteSOSRepository:

    def create(self, alert: SOSAlert) -> SOSAlert:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO sos_alerts (
                    id, ride_id, rider_id, rider_name, message,
                    latitude, longitude, active, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert.id,
                    alert.ride_id,
                    alert.rider_id,
                    alert.rider_name,
                    alert.message,
                    alert.latitude,
                    alert.longitude,
                    int(alert.active),
                    alert.created_at.isoformat(),
                ),
            )
        return alert

    def get_by_id(self, alert_id: str):
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM sos_alerts WHERE id = ?",
                (alert_id,),
            ).fetchone()

        return self._to_record(row)

    def list_by_ride(self, ride_id: str):
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM sos_alerts
                WHERE ride_id = ?
                ORDER BY created_at DESC
                """,
                (ride_id,),
            ).fetchall()

        return [self._to_record(row) for row in rows]

    def update(self, alert: SOSAlert) -> SOSAlert:
        with get_connection() as connection:
            cursor = connection.execute(
                """
                UPDATE sos_alerts
                SET active = ?
                WHERE id = ? AND ride_id = ?
                """,
                (int(alert.active), alert.id, alert.ride_id),
            )

            if cursor.rowcount == 0:
                raise ValueError(f"SOS alert '{alert.id}' does not exist.")

        return alert

    @staticmethod
    def _to_record(row):
        if row is None:
            return None

        return SOSAlert(
            id=row["id"],
            ride_id=row["ride_id"],
            rider_id=row["rider_id"],
            rider_name=row["rider_name"],
            message=row["message"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            active=bool(row["active"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
