"""Shared fakes and constants for the NLP tests. Imports neither pytest nor FastAPI, so the
service-level tests can run anywhere. Nothing here loads a real model."""
import tempfile
import threading
from pathlib import Path
from typing import Callable, Optional, Tuple

from app.nlp.qwen_lora_service import QwenLoraIntentService

# The 16 existing routes registered before the NLP additions (verified against the project's endpoint files).
EXISTING_ROUTES = frozenset({
    ("GET", "/api/v1/health"),
    ("POST", "/api/v1/rides"),
    ("POST", "/api/v1/rides/join"),
    ("GET", "/api/v1/rides/{ride_id}"),
    ("POST", "/api/v1/rides/{ride_id}/riders"),
    ("GET", "/api/v1/rides/{ride_id}/riders"),
    ("PATCH", "/api/v1/rides/{ride_id}/riders/{rider_id}/status"),
    ("PUT", "/api/v1/rides/{ride_id}/riders/{rider_id}/location"),
    ("GET", "/api/v1/rides/{ride_id}/locations"),
    ("POST", "/api/v1/rides/{ride_id}/chat"),
    ("GET", "/api/v1/rides/{ride_id}/chat"),
    ("GET", "/api/v1/route-intelligence/nearby"),
    ("POST", "/api/v1/sos/{ride_id}"),
    ("GET", "/api/v1/sos/{ride_id}"),
    ("PATCH", "/api/v1/sos/{ride_id}/{alert_id}/resolve"),
    ("POST", "/api/v1/push/subscribe"),
})
NEW_ROUTES = frozenset({
    ("POST", "/api/v1/nlp/predict"),
    ("GET", "/api/v1/nlp/status"),
})


class FakeBackend:
    """Stands in for the real model: returns a scripted reply and records how it was called."""

    def __init__(self, reply: str = "REFUELING", *, raise_exc: Optional[Exception] = None,
                 block_event: Optional[threading.Event] = None, entered_event: Optional[threading.Event] = None):
        self.reply = reply
        self.raise_exc = raise_exc
        self.block_event = block_event      # generate() waits on this (to simulate a slow model)
        self.entered_event = entered_event  # set as soon as generate() starts
        self.calls = []                     # (user_prompt, max_new_tokens)
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    def generate(self, user_prompt: str, max_new_tokens: int) -> str:
        with self._lock:
            self.calls.append((user_prompt, max_new_tokens))
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            if self.entered_event is not None:
                self.entered_event.set()
            if self.block_event is not None:
                self.block_event.wait(10)
            if self.raise_exc is not None:
                raise self.raise_exc
            return self.reply
        finally:
            with self._lock:
                self.active -= 1


def make_adapter_dir() -> tempfile.TemporaryDirectory:
    """A temp directory that looks like a valid adapter folder (files are empty placeholders)."""
    tmp = tempfile.TemporaryDirectory()
    (Path(tmp.name) / "adapter_config.json").write_text("{}", encoding="utf-8")
    (Path(tmp.name) / "adapter_model.safetensors").write_bytes(b"")
    return tmp


def make_service(
    backend: Optional[FakeBackend] = None, *, enabled: bool = True, loader: Optional[Callable] = None,
    return_raw_output: bool = False, queue_timeout_seconds: float = 10.0, start: bool = True,
) -> Tuple[QwenLoraIntentService, FakeBackend]:
    """Build a service wired to a fake backend. With start=True it loads in the background and this
    returns once loading has settled (READY, or FAILED if the supplied loader raises)."""
    backend = backend if backend is not None else FakeBackend()
    tmp = make_adapter_dir()
    service = QwenLoraIntentService(
        enabled=enabled,
        adapter_dir=Path(tmp.name),
        loader=loader if loader is not None else (lambda adapter_dir, base_model, local_only: backend),
        return_raw_output=return_raw_output,
        queue_timeout_seconds=queue_timeout_seconds,
    )
    service._tmp = tmp  # keep the temp directory alive for the service's lifetime
    if start:
        service.start_background_load()
        service.join_loader(10)
    return service, backend
