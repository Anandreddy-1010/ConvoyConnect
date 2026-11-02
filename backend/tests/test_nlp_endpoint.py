"""Endpoint tests (FastAPI TestClient). The model is replaced by a FAKE service injected through
FastAPI's dependency override, so no model is ever loaded here."""
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app as fastapi_app
from app.nlp import responses as R
from app.nlp.qwen_lora_service import MODEL_ID, QwenLoraIntentService, get_nlp_service
from tests.nlp_support import EXISTING_ROUTES, NEW_ROUTES, FakeBackend, make_service

PREDICT = "/api/v1/nlp/predict"
STATUS = "/api/v1/nlp/status"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


@pytest.fixture
def client_for():
    """client_for(service) -> TestClient whose NLP dependency is the given (fake) service."""
    def _make(service):
        fastapi_app.dependency_overrides[get_nlp_service] = lambda: service
        return TestClient(fastapi_app)
    yield _make
    fastapi_app.dependency_overrides.pop(get_nlp_service, None)


# ------------------------------------------------------------------ disabled by default
def test_code_defaults_are_off(monkeypatch):
    from app.core.config import Settings
    for name in ("NLP_ENABLED", "NLP_RETURN_RAW_OUTPUT", "NLP_ADAPTER_DIR", "NLP_LOCAL_FILES_ONLY"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    assert settings.NLP_ENABLED is False
    assert settings.NLP_RETURN_RAW_OUTPUT is False
    assert settings.NLP_ADAPTER_DIR == ""


def test_default_server_configuration_is_disabled_and_other_routes_still_work():
    get_nlp_service.cache_clear()                       # build the singleton under the hermetic test environment
    client = TestClient(fastapi_app)                    # NO dependency override: the real default service
    response = client.post(PREDICT, json={"text": "We are running low on fuel."})
    assert response.status_code == 503 and response.json() == {"detail": R.MSG_DISABLED}
    status = client.get(STATUS).json()
    assert status == {"enabled": False, "state": "disabled", "ready": False, "model": MODEL_ID}
    assert client.get("/api/v1/health").status_code == 200
    get_nlp_service.cache_clear()


# ------------------------------------------------------------------ request validation
def test_invalid_requests_are_rejected_before_the_model_is_called(client_for):
    service, backend = make_service()
    client = client_for(service)
    bad_bodies = [{}, {"text": ""}, {"text": "   "}, {"text": " \n\t "}, {"text": "x" * 501},
                  {"text": None}, {"text": 123}, {"txt": "typo"}, []]
    for body in bad_bodies:
        response = client.post(PREDICT, json=body)
        assert response.status_code == 422, f"{body!r} -> {response.status_code}"
    malformed = client.post(PREDICT, content="this is not json", headers={"Content-Type": "application/json"})
    assert malformed.status_code == 422
    assert backend.calls == [], "the model must never run for an invalid request"


def test_text_at_the_length_limit_is_accepted_and_whitespace_is_trimmed(client_for):
    service, _ = make_service()
    client = client_for(service)
    assert client.post(PREDICT, json={"text": "x" * 500}).status_code == 200
    body = client.post(PREDICT, json={"text": "  We are running low on fuel.  \n"}).json()
    assert body["input_text"] == "We are running low on fuel."


# ------------------------------------------------------------------ successful prediction
def test_successful_prediction_response_shape(client_for):
    service, backend = make_service(FakeBackend("REFUELING"))
    response = client_for(service).post(PREDICT, json={"text": "We are running low on fuel. We need to stop soon."})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"input_text", "predicted_intent", "model", "parse_succeeded", "parse_status", "latency_ms"}
    assert body["input_text"] == "We are running low on fuel. We need to stop soon."
    assert body["predicted_intent"] == "REFUELING"
    assert body["model"] == MODEL_ID
    assert body["parse_succeeded"] is True and body["parse_status"] == "exact"
    assert isinstance(body["latency_ms"], (int, float)) and body["latency_ms"] >= 0
    assert "raw_output" not in body, "raw output must be absent unless NLP_RETURN_RAW_OUTPUT=true"
    assert "confidence" not in body and "score" not in body
    assert len(backend.calls) == 1


def test_raw_output_is_only_returned_when_explicitly_enabled(client_for):
    service, _ = make_service(FakeBackend("REFUELING\n\nextra words"), return_raw_output=True)
    body = client_for(service).post(PREDICT, json={"text": "x"}).json()
    assert body["raw_output"] == "REFUELING\n\nextra words" and body["parse_status"] == "extracted"
    service2, _ = make_service(FakeBackend("REFUELING\n\nextra words"), return_raw_output=False)
    assert "raw_output" not in client_for(service2).post(PREDICT, json={"text": "x"}).json()


def test_unparseable_model_output_is_reported_explicitly_never_as_general(client_for):
    for reply, status in [("NESTED", "invalid_label"), ("", "empty_output"), ("LOST or REFUELING", "ambiguous_output")]:
        service, _ = make_service(FakeBackend(reply))
        response = client_for(service).post(PREDICT, json={"text": "x"})
        assert response.status_code == 200
        body = response.json()
        assert body["predicted_intent"] is None and body["parse_succeeded"] is False and body["parse_status"] == status
        assert "GENERAL" not in response.text, "a failed parse must never be reported as GENERAL"
        assert "raw_output" not in body


# ------------------------------------------------------------------ loading / failure / error states
def test_prediction_returns_503_while_loading_then_succeeds_when_ready(client_for):
    release, entered = threading.Event(), threading.Event()
    backend = FakeBackend()

    def slow_loader(adapter_dir, base_model, local_only):
        entered.set()
        release.wait(10)
        return backend

    service, _ = make_service(backend, loader=slow_loader, start=False)
    client = client_for(service)
    service.start_background_load()
    assert entered.wait(5)
    response = client.post(PREDICT, json={"text": "x"})
    assert response.status_code == 503
    assert response.json() == {"detail": R.MSG_LOADING} and response.headers["Retry-After"] == "5"
    assert client.get(STATUS).json()["state"] == "loading"
    release.set()
    service.join_loader(10)
    assert client.get(STATUS).json() == {"enabled": True, "state": "ready", "ready": True, "model": MODEL_ID}
    assert client.post(PREDICT, json={"text": "x"}).status_code == 200


def test_failed_load_returns_503_without_internal_details(client_for):
    def loader(adapter_dir, base_model, local_only):
        raise RuntimeError(r"secret C:\Users\private\adapter_model.safetensors corrupted")

    service, _ = make_service(loader=loader)
    client = client_for(service)
    response = client.post(PREDICT, json={"text": "x"})
    assert response.status_code == 503 and response.json() == {"detail": R.MSG_UNAVAILABLE}
    for text in (response.text, client.get(STATUS).text):
        for leak in ("secret", "private", "Traceback", "RuntimeError", "safetensors", "\\\\"):
            assert leak not in text, leak
    assert client.get(STATUS).json()["state"] == "failed"


def test_inference_error_returns_500_with_a_generic_message(client_for):
    service, _ = make_service(FakeBackend(raise_exc=RuntimeError("secret internal detail /home/x")))
    response = client_for(service).post(PREDICT, json={"text": "x"})
    assert response.status_code == 500 and response.json() == {"detail": R.MSG_INFERENCE}
    assert "secret" not in response.text and "/home" not in response.text


def test_status_endpoint_reports_only_the_state(client_for):
    disabled = QwenLoraIntentService(enabled=False, adapter_dir=Path("unused"))
    assert client_for(disabled).get(STATUS).json() == {"enabled": False, "state": "disabled", "ready": False, "model": MODEL_ID}
    ready, _ = make_service()
    assert set(client_for(ready).get(STATUS).json()) == {"enabled", "state", "ready", "model"}


# ------------------------------------------------------------------ routes still registered
def test_all_existing_routes_plus_the_new_nlp_routes_are_registered(client_for):
    registered = {(m, r.path) for r in fastapi_app.routes if hasattr(r, "methods") for m in r.methods}
    assert EXISTING_ROUTES <= registered, f"missing: {sorted(EXISTING_ROUTES - registered)}"
    assert NEW_ROUTES <= registered
    spec = TestClient(fastapi_app).get("/openapi.json").json()
    documented = {(m.upper(), p) for p, ops in spec["paths"].items() for m in ops if m in HTTP_METHODS}
    assert (EXISTING_ROUTES | NEW_ROUTES) <= documented


# ------------------------------------------------------------------ existing chat behaviour preserved
def test_chat_flow_is_unchanged_and_never_touches_the_nlp_model(monkeypatch):
    called = []

    def boom(*args, **kwargs):
        called.append(1)
        raise AssertionError("chat must never call the NLP model")

    monkeypatch.setattr(QwenLoraIntentService, "predict", boom)
    monkeypatch.setattr(QwenLoraIntentService, "start_background_load", boom)
    client = TestClient(fastapi_app)

    ride = client.post("/api/v1/rides", json={"ride_name": "NLP Isolation Run", "start_location_name": "Denver, CO",
                                              "destination_location_name": "Moab, UT", "leader_name": "Alex Rider"})
    assert ride.status_code == 201
    ride_id = ride.json()["id"]
    rider = client.post(f"/api/v1/rides/{ride_id}/riders", json={"name": "Sam Convoy", "bike_model": "Suzuki V-Strom"})
    assert rider.status_code == 201
    rider_id = rider.json()["id"]

    # An obvious refuelling message: it must be stored verbatim, with no intent attached, and no model call.
    chat = client.post(f"/api/v1/rides/{ride_id}/chat", json={"rider_id": rider_id, "text": "Pulling over for gas."})
    assert chat.status_code == 201 and chat.json()["rider_name"] == "Sam Convoy"
    assert "Pulling over for gas." in chat.text
    assert not any(k in chat.json() for k in ("intent", "predicted_intent", "nlp", "parse_status"))
    listing = client.get(f"/api/v1/rides/{ride_id}/chat")
    assert listing.status_code == 200 and len(listing.json()) == 1
    assert "Pulling over for gas." in listing.text
    assert called == [], "no NLP call may happen during ordinary ride/chat use"


# ------------------------------------------------------------------ startup (lifespan)
def test_startup_requests_background_loading_once_without_blocking(monkeypatch):
    import app.main as main_module
    started = []

    class SpyService:
        def start_background_load(self):
            started.append(1)
            return True

    monkeypatch.setattr(main_module, "get_nlp_service", lambda: SpyService())
    monkeypatch.setattr(main_module, "settings", main_module.settings.model_copy(update={"SEED_DEMO_DATA": False}))
    with TestClient(fastapi_app) as client:           # entering the context runs the lifespan startup
        assert client.get("/api/v1/health").status_code == 200
    assert started == [1]
