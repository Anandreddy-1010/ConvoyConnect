"""Service tests with a FAKE backend: state machine, background loading, failures, concurrency, paths.
No model is loaded and no FastAPI is needed."""
import logging
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import pytest

from app.nlp.intent_parsing import MAX_NEW_TOKENS, ParseStatus, build_prompt
from app.nlp.qwen_lora_service import (
    DEFAULT_BASE_MODEL, AdapterNotFoundError, NLPBusyError, NLPDisabledError, NLPInferenceError,
    NLPNotReadyError, NLPState, NLPUnavailableError, QwenLoraIntentService, default_adapter_dir,
    repo_root, resolve_adapter_dir, validate_adapter_dir,
)
from tests.nlp_support import FakeBackend, make_adapter_dir, make_service

BACKEND_DIR = Path(__file__).resolve().parents[1]


class _LogCapture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)

    @property
    def text(self):
        return "\n".join(r.getMessage() + (" | " + str(r.exc_info[1]) if r.exc_info else "") for r in self.records)


def _capture():
    handler = _LogCapture()
    logger = logging.getLogger("convoyconnect.nlp")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    return handler, logger


# ------------------------------------------------------------------ disabled by default / not started
def test_disabled_service_never_loads_and_predict_is_refused():
    loads = []
    service, _ = make_service(enabled=False, loader=lambda *a: loads.append(1), start=False)
    assert service.state is NLPState.DISABLED
    assert service.start_background_load() is False
    assert loads == []
    with pytest.raises(NLPDisabledError):
        service.predict("anything")


def test_enabled_but_not_started_is_not_ready():
    service, _ = make_service(start=False)
    assert service.state is NLPState.NOT_STARTED
    with pytest.raises(NLPNotReadyError):
        service.predict("hi")


# ------------------------------------------------------------------ background loading
def test_loading_happens_in_a_background_thread_and_requests_get_not_ready():
    release, entered = threading.Event(), threading.Event()
    backend = FakeBackend()

    def slow_loader(adapter_dir, base_model, local_only):
        entered.set()
        release.wait(10)
        return backend

    service, _ = make_service(backend, loader=slow_loader, start=False)
    main_thread = threading.current_thread()
    assert service.start_background_load() is True          # returns immediately, does not block on the loader
    assert entered.wait(5)
    assert service.state is NLPState.LOADING
    with pytest.raises(NLPNotReadyError):
        service.predict("x")
    assert service._load_thread is not main_thread and service._load_thread.daemon
    release.set()
    service.join_loader(10)
    assert service.state is NLPState.READY
    assert service.predict("need gas").intent == "REFUELING"


def test_concurrent_starts_trigger_exactly_one_load():
    calls, calls_lock, results = [], threading.Lock(), []
    backend = FakeBackend()

    def loader(adapter_dir, base_model, local_only):
        with calls_lock:
            calls.append(1)
        threading.Event().wait(0.2)   # widen the race window
        return backend

    service, _ = make_service(backend, loader=loader, start=False)
    barrier = threading.Barrier(20)

    def start():
        barrier.wait()
        results.append(service.start_background_load())

    threads = [threading.Thread(target=start) for _ in range(20)]
    [t.start() for t in threads]
    [t.join(10) for t in threads]
    service.join_loader(10)
    assert results.count(True) == 1 and results.count(False) == 19
    assert len(calls) == 1, "the model must load exactly once"
    assert service.state is NLPState.READY
    assert service.start_background_load() is False         # still idempotent afterwards


# ------------------------------------------------------------------ load failures
def test_load_failure_marks_failed_and_hides_details_from_callers_but_logs_them():
    handler, logger = _capture()
    try:
        def loader(adapter_dir, base_model, local_only):
            raise RuntimeError(r"secret C:\Users\private\model.bin corrupted")

        service, _ = make_service(loader=loader)
        assert service.state is NLPState.FAILED
        with pytest.raises(NLPUnavailableError) as info:
            service.predict("x")
        assert "secret" not in str(info.value) and "private" not in str(info.value)
        assert "secret" not in repr(service.status())
        assert "secret" in handler.text, "the real cause must be in the server log"
    finally:
        logger.removeHandler(handler)


def test_failed_load_is_not_retried_by_later_requests():
    attempts = []

    def loader(adapter_dir, base_model, local_only):
        attempts.append(1)
        raise RuntimeError("boom")

    service, _ = make_service(loader=loader)
    for _ in range(3):
        with pytest.raises(NLPUnavailableError):
            service.predict("x")
    assert service.start_background_load() is False
    assert len(attempts) == 1


def test_missing_optional_dependencies_fail_cleanly_with_install_hint():
    handler, logger = _capture()
    try:
        def loader(adapter_dir, base_model, local_only):
            raise ImportError("No module named 'torch'")

        service, _ = make_service(loader=loader)
        assert service.state is NLPState.FAILED
        assert "requirements-nlp.txt" in handler.text
    finally:
        logger.removeHandler(handler)


def test_missing_adapter_fails_before_the_loader_is_called():
    loads = []
    service = QwenLoraIntentService(enabled=True, adapter_dir=Path(tempfile.gettempdir()) / "definitely_not_an_adapter_dir",
                                    loader=lambda *a: loads.append(1))
    service.start_background_load()
    service.join_loader(10)
    assert service.state is NLPState.FAILED and loads == []


def test_adapter_directory_validation():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        with pytest.raises(AdapterNotFoundError):
            validate_adapter_dir(root / "missing")
        with pytest.raises(AdapterNotFoundError):
            validate_adapter_dir(root)                       # empty dir
        (root / "adapter_config.json").write_text("{}", encoding="utf-8")
        with pytest.raises(AdapterNotFoundError):
            validate_adapter_dir(root)                       # config but no weights
        (root / "adapter_model.bin").write_bytes(b"")
        validate_adapter_dir(root)                           # .bin accepted
    tmp = make_adapter_dir()
    validate_adapter_dir(Path(tmp.name))                     # .safetensors accepted
    tmp.cleanup()


# ------------------------------------------------------------------ inference
def test_prediction_uses_training_prompt_and_eval_decoding_settings():
    service, backend = make_service(FakeBackend("REFUELING"))
    text = "We are running low on fuel. We need to stop soon."
    result = service.predict(text)
    assert (result.intent, result.status, result.succeeded) == ("REFUELING", ParseStatus.EXACT, True)
    assert result.raw_output == "REFUELING" and result.latency_ms >= 0
    assert backend.calls == [(build_prompt(text), MAX_NEW_TOKENS)]
    assert MAX_NEW_TOKENS == 12


def test_malformed_output_is_reported_not_converted_to_general():
    for reply, status in [("NESTED", ParseStatus.INVALID_LABEL), ("", ParseStatus.EMPTY_OUTPUT),
                          ("LOST or REFUELING", ParseStatus.AMBIGUOUS_OUTPUT)]:
        service, _ = make_service(FakeBackend(reply))
        result = service.predict("x")
        assert result.intent is None and result.succeeded is False and result.status == status, reply


def test_extra_explanation_after_the_label_is_handled():
    service, _ = make_service(FakeBackend("TRAFFIC_DELAY\n\nBecause the road is jammed."))
    result = service.predict("x")
    assert (result.intent, result.status) == ("TRAFFIC_DELAY", ParseStatus.EXTRACTED)


def test_inference_error_is_wrapped_without_details_and_releases_the_lock():
    handler, logger = _capture()
    try:
        backend = FakeBackend(raise_exc=RuntimeError("secret internal detail /home/x"))
        service, _ = make_service(backend, queue_timeout_seconds=0.2)
        with pytest.raises(NLPInferenceError) as info:
            service.predict("x")
        assert "secret" not in str(info.value) and info.value.__cause__ is None
        assert "secret" in handler.text
        backend.raise_exc = None
        assert service.predict("x").intent == "REFUELING", "lock must be released after a failed inference"
    finally:
        logger.removeHandler(handler)


def test_rider_message_text_is_never_logged():
    handler, logger = _capture()
    try:
        service, _ = make_service()
        service.predict("PRIVATE-RIDER-MESSAGE-12345")
        assert "PRIVATE-RIDER-MESSAGE-12345" not in handler.text
        assert "text_chars=" in handler.text
    finally:
        logger.removeHandler(handler)


def test_inference_is_serialised_one_at_a_time():
    backend = FakeBackend()
    service, _ = make_service(backend, queue_timeout_seconds=10)
    outcomes = []

    def work():
        outcomes.append(service.predict("x").intent)

    threads = [threading.Thread(target=work) for _ in range(8)]
    [t.start() for t in threads]
    [t.join(15) for t in threads]
    assert outcomes == ["REFUELING"] * 8
    assert backend.max_active == 1


def test_busy_when_the_inference_slot_is_not_free_within_the_timeout():
    release, entered = threading.Event(), threading.Event()
    backend = FakeBackend(block_event=release, entered_event=entered)
    service, _ = make_service(backend, queue_timeout_seconds=0.05)
    first = threading.Thread(target=lambda: service.predict("slow"))
    first.start()
    assert entered.wait(5)
    with pytest.raises(NLPBusyError):
        service.predict("second")
    release.set()
    first.join(10)
    assert service.predict("third").intent == "REFUELING"


# ------------------------------------------------------------------ status never leaks internals
def test_status_contains_only_safe_fields():
    service, _ = make_service()
    status = service.status()
    assert set(status) == {"enabled", "state", "ready", "model"}
    assert status["state"] == "ready" and status["ready"] is True and status["enabled"] is True
    blob = repr(status)
    assert "\\" not in blob and "/" not in blob.replace("Qwen2.5-0.5B-Instruct + LoRA (ConvoyConnect Phase 3.7)", "")


# ------------------------------------------------------------------ adapter path resolution
def test_default_adapter_path_is_resolved_from_the_source_location_not_the_cwd():
    expected = repo_root() / "research" / "nlp" / "advanced_llm" / "models" / "lora_adapter"
    assert default_adapter_dir() == expected
    assert (repo_root() / "backend" / "app" / "nlp").is_dir(), "repo_root() must be the folder that contains backend/"
    original = os.getcwd()
    with tempfile.TemporaryDirectory() as elsewhere:
        os.chdir(elsewhere)
        try:
            assert default_adapter_dir() == expected
            assert resolve_adapter_dir("") == expected and resolve_adapter_dir("   ") == expected
        finally:
            os.chdir(original)


def test_configured_adapter_path_rules():
    assert resolve_adapter_dir("research/custom_adapter") == (repo_root() / "research" / "custom_adapter").resolve()
    with tempfile.TemporaryDirectory() as d:
        assert resolve_adapter_dir(d) == Path(d).resolve()


def test_real_adapter_folder_in_the_repo_matches_the_documented_configuration():
    import json
    config_file = default_adapter_dir() / "adapter_config.json"
    if not config_file.exists():
        pytest.skip("adapter_config.json not present in this checkout")
    cfg = json.loads(config_file.read_text(encoding="utf-8"))
    assert cfg["base_model_name_or_path"] == DEFAULT_BASE_MODEL
    assert cfg["r"] == 8 and cfg["lora_alpha"] == 16
    assert set(cfg["target_modules"]) == {"q_proj", "k_proj", "v_proj", "o_proj"}


# ------------------------------------------------------------------ optional dependencies stay optional
def test_importing_the_service_does_not_import_torch_transformers_or_peft():
    code = ("import sys; import app.nlp.qwen_lora_service, app.nlp.responses, app.nlp.intent_parsing; "
            "bad = [m for m in ('torch', 'transformers', 'peft') if m in sys.modules]; "
            "print(','.join(bad)); sys.exit(1 if bad else 0)")
    proc = subprocess.run([sys.executable, "-c", code], cwd=str(BACKEND_DIR), capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, f"heavy modules were imported at import time: {proc.stdout.strip()} {proc.stderr[-300:]}"
