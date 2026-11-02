"""
app/api/v1/endpoints/nlp.py
------------------------------
Optional NLP intent prediction (Phase 3.8):

  POST /api/v1/nlp/predict   classify one rider message into one of the 12 trained intents
  GET  /api/v1/nlp/status    report whether the model is disabled / loading / ready / failed

SAFETY BOUNDARY: this router is STANDALONE. It is not called by chat, rides, riders, locations
or any alerting/navigation code, and a prediction never triggers an action. Predictions are
advisory only. (tests/test_nlp_static_guards.py enforces the separation.)

DISABLED BY DEFAULT: with NLP_ENABLED=false, /predict answers 503 and nothing is loaded.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from app.nlp.qwen_lora_service import MODEL_ID, NLPServiceError, QwenLoraIntentService, get_nlp_service
from app.nlp.responses import build_prediction_payload, http_error_for
from app.schemas.common import ErrorResponse
from app.schemas.nlp import IntentPredictionRequest, IntentPredictionResponse, NLPStatusResponse

logger = logging.getLogger("convoyconnect.nlp")

router = APIRouter()


@router.post(
    "/predict",
    response_model=IntentPredictionResponse,  # documents the schema; the body is built by build_prediction_payload()
    summary="Predict the intent of a rider message (advisory only)",
    description=(
        "Classifies one message into one of 12 intents using the Phase 3.7 Qwen2.5-0.5B-Instruct + "
        "LoRA model on CPU. The result is advisory: it is NOT used to trigger alerts, SOS, navigation "
        "or any other action. `predicted_intent` is null (with `parse_succeeded=false`) when the model "
        "output cannot be validated. No confidence score is provided."
    ),
    responses={
        500: {"model": ErrorResponse, "description": "Inference failed (details are in the server log only)."},
        503: {"model": ErrorResponse, "description": "NLP disabled, still loading, unavailable, or busy."},
    },
)
def predict_intent(
    request: IntentPredictionRequest,
    service: QwenLoraIntentService = Depends(get_nlp_service),
):
    try:
        result = service.predict(request.text)
    except Exception as exc:  # NLPServiceError subclasses -> mapped; anything else -> generic 500
        if not isinstance(exc, NLPServiceError):
            logger.exception("Unexpected error in POST /nlp/predict")
        spec = http_error_for(exc)
        raise HTTPException(status_code=spec.status_code, detail=spec.detail, headers=spec.headers) from None

    payload = build_prediction_payload(
        input_text=request.text,
        result=result,
        model_id=MODEL_ID,
        include_raw_output=service.return_raw_output,
    )
    # Returned as-is (not re-validated) so 'raw_output' is absent - not null - unless explicitly enabled,
    # independent of FastAPI/pydantic version details. The payload shape is unit-tested.
    return JSONResponse(content=payload)


@router.get(
    "/status",
    response_model=NLPStatusResponse,
    summary="NLP model status",
    description="Reports only the loading state (disabled / not_started / loading / ready / failed). "
    "Never includes paths or error details.",
)
def nlp_status(service: QwenLoraIntentService = Depends(get_nlp_service)):
    return service.status()
