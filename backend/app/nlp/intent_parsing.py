"""
Intent labels, prompt construction and model-output parsing for the
Phase 3.7 Qwen2.5-0.5B-Instruct + LoRA intent classifier.

PURE MODULE: standard library only (no torch, no FastAPI, no pydantic), so it
can be imported and unit-tested anywhere.

IMPORTANT - these definitions must stay byte-for-byte consistent with how the
adapter was trained and evaluated (research/nlp/advanced_llm/scripts/):
  * INTENT_LABELS      == "intent_labels" in scripts/config.json (same names, same order)
  * build_prompt()     == build_prompt() in scripts/common.py
  * MAX_NEW_TOKENS     == "zero_shot.max_new_tokens" in scripts/config.json
tests/test_nlp_parsing.py fails if any of these drift.

The model is NOT a calibrated probabilistic classifier here: it generates text.
Nothing in this module produces, estimates or implies a confidence score.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional, Sequence

INTENT_LABELS: tuple[str, ...] = (
    "REFUELING",
    "REST_BREAK",
    "FOOD_BREAK",
    "VEHICLE_PROBLEM",
    "TRAFFIC_DELAY",
    "FALLING_BEHIND",
    "LOST",
    "REGROUP_REQUEST",
    "DESTINATION_CHANGE",
    "EMERGENCY",
    "STATUS_UPDATE",
    "GENERAL",
)

# Same value used during evaluation. Do not raise it: the evaluated behaviour used 12.
MAX_NEW_TOKENS = 12


class ParseStatus:
    """Why a prediction was (or was not) accepted. Plain string constants (JSON friendly)."""
    EXACT = "exact"                      # the whole reply is one allowed label
    EXTRACTED = "extracted"              # reply starts with an allowed label, followed by extra text
    INVALID_LABEL = "invalid_label"      # reply does not start with an allowed label
    EMPTY_OUTPUT = "empty_output"        # reply is empty / whitespace
    AMBIGUOUS_OUTPUT = "ambiguous_output"  # label first, but the reply also names a different label

    ALL = (EXACT, EXTRACTED, INVALID_LABEL, EMPTY_OUTPUT, AMBIGUOUS_OUTPUT)
    SUCCESS = (EXACT, EXTRACTED)


@dataclass(frozen=True)
class ParseResult:
    intent: Optional[str]  # an allowed label, or None whenever parsing did not succeed
    status: str            # one of ParseStatus.ALL

    @property
    def succeeded(self) -> bool:
        return self.status in ParseStatus.SUCCESS and self.intent is not None


def build_prompt(message: str, labels: Sequence[str] = INTENT_LABELS) -> str:
    """The user-turn text the adapter was trained on (identical to research/.../common.py)."""
    label_list = ", ".join(labels)
    return (
        "You are classifying a motorcycle group-ride chat message into exactly one intent category.\n"
        f"Categories: {label_list}\n\n"
        f"Message: \"{message}\"\n\n"
        "Reply with ONLY the single category name from the list above, nothing else."
    )


_WRAPPER_CHARS = "\"'`*. "
_LEADING = re.compile(r"^[\s\"'`*]*([A-Za-z_]+)")
_WORD = re.compile(r"[A-Za-z_]+")


def parse_model_output(raw: str, labels: Sequence[str] = INTENT_LABELS) -> ParseResult:
    """Validate the model's reply against the allowed labels.

    Rules (deliberately conservative - a wrong guess is worse than no answer):
      1. Empty / whitespace reply                          -> EMPTY_OUTPUT
      2. Whole reply is a label (case-insensitive, ignoring
         surrounding quotes / backticks / asterisks / '.')  -> EXACT
      3. Reply STARTS with a label as a complete word
         (so REFUELING_STATION is not REFUELING):
           - if any DIFFERENT allowed label is named later  -> AMBIGUOUS_OUTPUT (no intent returned)
           - otherwise                                       -> EXTRACTED
      4. Anything else (invented category, prose, etc.)     -> INVALID_LABEL
    A failed parse NEVER falls back to a default label such as GENERAL.
    """
    allowed = {label.upper() for label in labels}
    text = (raw or "").strip()
    if not text:
        return ParseResult(None, ParseStatus.EMPTY_OUTPUT)

    whole = text.strip(_WRAPPER_CHARS).upper()
    if whole in allowed:
        return ParseResult(whole, ParseStatus.EXACT)

    match = _LEADING.match(text)
    first = match.group(1).upper() if match else ""
    if first in allowed:
        later_words = {w.upper() for w in _WORD.findall(text[match.end():])}
        if later_words & (allowed - {first}):
            return ParseResult(None, ParseStatus.AMBIGUOUS_OUTPUT)
        return ParseResult(first, ParseStatus.EXTRACTED)

    return ParseResult(None, ParseStatus.INVALID_LABEL)
