"""
Framework-free helpers for the NLP HTTP layer (pure functions, standard library only).

The FastAPI endpoint (app/api/v1/endpoints/nlp.py) is a thin shell around these, so the
security-relevant decisions - which message a client may see for each failure, and which
fields are returned - are unit-testable without FastAPI.

Client-facing messages are FIXED STRINGS. They never contain exception text, stack traces,
file-system paths, or model internals; details go to the server log only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.nlp.qwen_lora_service import (
    NLPBusyError,
    NLPDisabledError,
    NLPInferenceError,
    NLPNotReadyError,
    NLPUnavailableError,
    PredictionResult,
)

MSG_DISABLED = "NLP prediction is disabled on this server."
MSG_LOADING = "The NLP model is still loading. Please retry shortly."
MSG_UNAVAILABLE = "The NLP model is unavailable."
MSG_BUSY = "The NLP model is busy. Please retry shortly."
MSG_INFERENCE = "The NLP model could not process this request."


@dataclass(frozen=True)
class HttpErrorSpec:
    status_code: int
    detail: str
    headers: Optional[dict[str, str]] = None


def http_error_for(exc: Exception) -> HttpErrorSpec:
    """Map a service exception to a safe HTTP error. Unknown exceptions map to a generic 500."""
    if isinstance(exc, NLPDisabledError):
        return HttpErrorSpec(503, MSG_DISABLED)
    if isinstance(exc, NLPNotReadyError):
        return HttpErrorSpec(503, MSG_LOADING, {"Retry-After": "5"})
    if isinstance(exc, NLPUnavailableError):
        return HttpErrorSpec(503, MSG_UNAVAILABLE)
    if isinstance(exc, NLPBusyError):
        return HttpErrorSpec(503, MSG_BUSY, {"Retry-After": "2"})
    return HttpErrorSpec(500, MSG_INFERENCE)  # NLPInferenceError and anything unexpected


def build_prediction_payload(
    *, input_text: str, result: PredictionResult, model_id: str, include_raw_output: bool
) -> dict[str, Any]:
    """Build the response body. Keys that are absent are NOT part of the response, so
    'raw_output' only appears when include_raw_output is True. There is deliberately no
    confidence field: generated text is not a calibrated probability."""
    payload: dict[str, Any] = {
        "input_text": input_text,
        "predicted_intent": result.intent,   # None (-> JSON null) when parsing failed
        "model": model_id,
        "parse_succeeded": result.succeeded,
        "parse_status": result.status,
        "latency_ms": round(result.latency_ms, 1),
    }
    if include_raw_output:
        payload["raw_output"] = result.raw_output
    return payload
