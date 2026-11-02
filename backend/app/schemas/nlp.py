"""
app/schemas/nlp.py
--------------------
Request / response models for the optional NLP intent-prediction endpoints (Phase 3.8).

There is deliberately NO confidence field: the model generates text, and generated text is
not a calibrated probability.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

MAX_TEXT_CHARS = 500


class IntentPredictionRequest(BaseModel):
    """Body for POST /api/v1/nlp/predict."""

    text: str = Field(
        ...,
        max_length=MAX_TEXT_CHARS,
        description=f"Rider message to classify (1-{MAX_TEXT_CHARS} characters, not blank).",
        examples=["We are running low on fuel. We need to stop soon."],
    )

    @field_validator("text")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text must not be empty or whitespace-only")
        return value


class IntentPredictionResponse(BaseModel):
    input_text: str
    predicted_intent: Optional[str] = Field(
        default=None,
        description="One of the 12 trained intent labels, or null when the model output could not be "
        "validated (see parse_status). Never defaults to GENERAL.",
    )
    model: str = Field(description="Identifier of the model that produced the prediction.")
    parse_succeeded: bool
    parse_status: Literal["exact", "extracted", "invalid_label", "empty_output", "ambiguous_output"]
    latency_ms: Optional[float] = Field(default=None, description="Model generation time in milliseconds.")
    raw_output: Optional[str] = Field(
        default=None,
        description="The model's raw generated text. Present ONLY when the server runs with "
        "NLP_RETURN_RAW_OUTPUT=true; omitted otherwise.",
    )


class NLPStatusResponse(BaseModel):
    enabled: bool
    state: Literal["disabled", "not_started", "loading", "ready", "failed"]
    ready: bool
    model: str
