import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import Lock

DATABASE_PATH = Path(__file__).resolve().parents[3] / "data" / "convoyconnect.db"
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

_db_lock = Lock()


@contextmanager
def get_connection():
    connection = sqlite3.connect(DATABASE_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database():
    with _db_lock:
        with get_connection() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS rides (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    invite_code TEXT NOT NULL UNIQUE,
                    created_by_rider_id TEXT NOT NULL,
                    start_location_name TEXT NOT NULL,
                    destination_location_name TEXT NOT NULL,
                    start_latitude REAL,
                    start_longitude REAL,
                    destination_latitude REAL,
                    destination_longitude REAL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS riders (
                    id TEXT PRIMARY KEY,
                    ride_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    status TEXT NOT NULL,
                    phone TEXT,
                    bike_model TEXT,
                    joined_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_riders_ride_id
                ON riders(ride_id);

                CREATE TABLE IF NOT EXISTS locations (
                    rider_id TEXT PRIMARY KEY,
                    ride_id TEXT NOT NULL,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    speed_kmh REAL,
                    heading_deg REAL,
                    recorded_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_locations_ride_id
                ON locations(ride_id);

                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    ride_id TEXT NOT NULL,
                    rider_id TEXT,
                    text TEXT NOT NULL,
                    message_type TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_chat_ride_id
                ON chat_messages(ride_id);

                CREATE TABLE IF NOT EXISTS sos_alerts (
                    id TEXT PRIMARY KEY,
                    ride_id TEXT NOT NULL,
                    rider_id TEXT NOT NULL,
                    rider_name TEXT NOT NULL,
                    message TEXT NOT NULL,
                    latitude REAL,
                    longitude REAL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_sos_ride_id
                ON sos_alerts(ride_id);
            """)

            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(locations)")
            }

            if "speed_kmh" not in columns:
                connection.execute(
                    "ALTER TABLE locations ADD COLUMN speed_kmh REAL"
                )
                if "speed_mph" in columns:
                    connection.execute(
                        "UPDATE locations SET speed_kmh = speed_mph * 1.609344 "
                        "WHERE speed_mph IS NOT NULL"
                    )


if __name__ == "__main__":
    initialize_database()
    print("SQLite database initialized successfully.")
    print("Database:", DATABASE_PATH)
