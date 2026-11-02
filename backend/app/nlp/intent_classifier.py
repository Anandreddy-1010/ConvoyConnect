"""
app/nlp/intent_classifier.py
-------------------------------
STUB — NOT IMPLEMENTED. See app/nlp/README.md.

Defines the intended interface for Phase 3's intent classification so
other modules can be written against a stable contract now. Calling
`classify()` today raises NotImplementedError on purpose — there is no
model loaded, and no endpoint currently calls this class.
"""

from dataclasses import dataclass
from enum import Enum


class Intent(str, Enum):
    FIND_RIDER = "find_rider"
    REPORT_DELAY = "report_delay"
    REQUEST_REROUTE = "request_reroute"
    GENERAL_QUESTION = "general_question"
    UNKNOWN = "unknown"


@dataclass
class IntentClassificationResult:
    intent: Intent
    confidence: float


class IntentClassifier:
    """Planned Phase 3 component. Will likely wrap a fine-tuned
    transformer model (e.g. DistilBERT) for short-text classification."""

    def __init__(self, model_path: str | None = None):
        self.model_path = model_path
        # TODO(Phase 3): load a trained model/tokenizer here.

    def classify(self, text: str) -> IntentClassificationResult:
        raise NotImplementedError(
            "IntentClassifier.classify() is not implemented yet. "
            "NLP intent classification is planned for Phase 3."
        )
