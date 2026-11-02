import json
import os
from pathlib import Path
from threading import Lock

from pywebpush import WebPushException, webpush


class PushService:
    def __init__(self):
        self._lock = Lock()
        self._storage_file = (
            Path(__file__).resolve().parents[2]
            / "data"
            / "push_subscriptions.json"
        )
        self._storage_file.parent.mkdir(parents=True, exist_ok=True)

        self._private_key = os.getenv(
            "VAPID_PRIVATE_KEY_FILE", "vapid_private.pem"
        )
        self._public_key = os.getenv(
            "VAPID_PUBLIC_KEY",
            "BPj0XvDQY5jPkWttJcyA-HghDx5gndbFWrB4-ILF9gaNgg0zL0j7OqXIZ99073jOoON5YnjOhXEhgmW7ryYJXuI",
        )
        self._subject = os.getenv(
            "VAPID_SUBJECT", "mailto:admin@example.com"
        )

        self._subscriptions = self._load_subscriptions()

    def _load_subscriptions(self):
        if not self._storage_file.exists():
            return {}

        try:
            with self._storage_file.open("r", encoding="utf-8") as file:
                data = json.load(file)

            return {
                (item["ride_id"], item["rider_id"]): item["subscription"]
                for item in data
            }
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            print(f"Could not load push subscriptions: {exc}")
            return {}

    def _save_subscriptions(self):
        data = [
            {
                "ride_id": ride_id,
                "rider_id": rider_id,
                "subscription": subscription,
            }
            for (ride_id, rider_id), subscription in self._subscriptions.items()
        ]

        temp_file = self._storage_file.with_suffix(".tmp")

        with temp_file.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2)

        temp_file.replace(self._storage_file)

    def save_subscription(self, ride_id, rider_id, subscription):
        if not subscription.get("endpoint"):
            raise ValueError("Push subscription endpoint is required.")

        with self._lock:
            self._subscriptions[(ride_id, rider_id)] = subscription
            self._save_subscriptions()

    def _send_push(self, key, subscription, payload):
        try:
            webpush(
                subscription_info=subscription,
                data=json.dumps(payload),
                vapid_private_key=self._private_key,
                vapid_claims={"sub": self._subject},
                ttl=60,
            )
            print(f"Push notification sent to rider {key[1]}")

        except WebPushException as exc:
            print(f"Push delivery failed for rider {key[1]}")
            print("Exception status:", exc.status_code)
            print("Exception message:", str(exc))

    def notify_other_riders(self, ride_id, sender_id, alert):
        """Existing emergency SOS notifications."""

        if not self._public_key:
            print("Push notifications skipped: VAPID_PUBLIC_KEY is not configured.")
            return

        with self._lock:
            targets = [
                (key, subscription)
                for key, subscription in self._subscriptions.items()
                if key[0] == ride_id and key[1] != sender_id
            ]

        payload = {
            "title": "ConvoyConnect - Emergency SOS",
            "body": f"{alert.rider_name}: {alert.message}",
            "url": "/",
            "tag": f"convoyconnect-sos-{alert.id}",
        }

        for key, subscription in targets:
            self._send_push(key, subscription, payload)
