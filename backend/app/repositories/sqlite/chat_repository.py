from datetime import datetime

from app.models.chat import ChatMessageRecord
from app.repositories.base import ChatRepository
from app.repositories.sqlite.database import get_connection


class SQLiteChatRepository(ChatRepository):

    def create(self, message: ChatMessageRecord) -> ChatMessageRecord:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO chat_messages (
                    id, ride_id, rider_id, text,
                    message_type, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    message.id,
                    message.ride_id,
                    message.rider_id,
                    message.text,
                    message.message_type,
                    message.created_at.isoformat(),
                ),
            )
        return message

    def list_by_ride(self, ride_id: str):
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM chat_messages
                WHERE ride_id = ?
                ORDER BY created_at
                """,
                (ride_id,),
            ).fetchall()

        return [
            ChatMessageRecord(
                id=row["id"],
                ride_id=row["ride_id"],
                rider_id=row["rider_id"],
                text=row["text"],
                message_type=row["message_type"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]
