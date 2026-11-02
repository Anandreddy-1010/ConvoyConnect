"""
app/nlp/entity_extractor.py
------------------------------
STUB — NOT IMPLEMENTED. See app/nlp/README.md.

Intended interface for Phase 3's Named Entity Recognition (extracting
rider names, place names, and time expressions from chat/query text).
Nothing here is called by any endpoint yet.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class ExtractedEntities:
    rider_names: List[str] = field(default_factory=list)
    place_names: List[str] = field(default_factory=list)
    time_expressions: List[str] = field(default_factory=list)


class EntityExtractor:
    """Planned Phase 3 component. Will likely start as a rule-based /
    spaCy pipeline before evaluating a fine-tuned NER model."""

    def extract(self, text: str) -> ExtractedEntities:
        raise NotImplementedError(
            "EntityExtractor.extract() is not implemented yet. "
            "Named entity recognition is planned for Phase 3."
        )
