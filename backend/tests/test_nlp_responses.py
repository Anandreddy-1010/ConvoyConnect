"""HTTP-layer helper tests: safe error messages and the response payload. Pure Python."""
import re

from app.nlp import responses as R
from app.nlp.qwen_lora_service import (
    MODEL_ID, NLPBusyError, NLPDisabledError, NLPInferenceError, NLPNotReadyError, NLPUnavailableError, PredictionResult,
)

LEAK = re.compile(r"[A-Za-z]:\\|/research|/home/|Traceback|\.py\b|RuntimeError|Exception|adapter_model")


def test_error_mapping():
    expected = {
        NLPDisabledError: (503, R.MSG_DISABLED, None),
        NLPNotReadyError: (503, R.MSG_LOADING, {"Retry-After": "5"}),
        NLPUnavailableError: (503, R.MSG_UNAVAILABLE, None),
        NLPBusyError: (503, R.MSG_BUSY, {"Retry-After": "2"}),
        NLPInferenceError: (500, R.MSG_INFERENCE, None),
    }
    for exc_type, (status, detail, headers) in expected.items():
        spec = R.http_error_for(exc_type())
        assert (spec.status_code, spec.detail, spec.headers) == (status, detail, headers), exc_type.__name__


def test_unknown_exceptions_map_to_a_generic_500_that_hides_the_message():
    spec = R.http_error_for(ValueError(r"secret C:\Users\x\model.bin"))
    assert spec.status_code == 500 and spec.detail == R.MSG_INFERENCE and "secret" not in spec.detail


def test_client_messages_never_contain_paths_or_stack_trace_markers():
    for message in (R.MSG_DISABLED, R.MSG_LOADING, R.MSG_UNAVAILABLE, R.MSG_BUSY, R.MSG_INFERENCE):
        assert not LEAK.search(message), message


def _result(intent="REFUELING", status="exact", raw="REFUELING", latency=1234.567):
    return PredictionResult(intent, status, raw, latency)


def test_payload_without_raw_output_by_default():
    payload = R.build_prediction_payload(input_text="t", result=_result(), model_id=MODEL_ID, include_raw_output=False)
    assert set(payload) == {"input_text", "predicted_intent", "model", "parse_succeeded", "parse_status", "latency_ms"}
    assert payload["latency_ms"] == 1234.6 and payload["parse_succeeded"] is True and payload["model"] == MODEL_ID


def test_payload_includes_raw_output_only_when_enabled():
    payload = R.build_prediction_payload(input_text="t", result=_result(), model_id=MODEL_ID, include_raw_output=True)
    assert payload["raw_output"] == "REFUELING"


def test_failed_parse_payload_is_explicit_and_has_no_default_label():
    payload = R.build_prediction_payload(
        input_text="t", result=_result(None, "invalid_label", "NESTED"), model_id=MODEL_ID, include_raw_output=False)
    assert payload["predicted_intent"] is None and payload["parse_succeeded"] is False
    assert payload["parse_status"] == "invalid_label" and "NESTED" not in repr(payload)


def test_no_confidence_field_anywhere():
    for raw in (True, False):
        payload = R.build_prediction_payload(input_text="t", result=_result(), model_id=MODEL_ID, include_raw_output=raw)
        assert not any("confidence" in key or "score" in key or "probab" in key for key in payload)
