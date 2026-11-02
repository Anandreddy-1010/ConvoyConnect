"""OPT-IN test with the REAL Qwen2.5-0.5B-Instruct + LoRA model on CPU.

Skipped unless RUN_MODEL_TESTS=1. Needs torch / transformers / peft (requirements-nlp.txt), the adapter in
research/nlp/advanced_llm/models/lora_adapter, and the base model (downloaded to the Hugging Face cache on
first use). Takes roughly 1-2 minutes.

It replays real Phase 3.7 evaluation examples through the SERVICE and checks that the service reaches the same
parsed outcome as the stored evaluation - proving that the service's decoding setup matches what was evaluated.
"""
import json
import os
import warnings
from pathlib import Path

import pytest

from app.nlp.intent_parsing import ParseStatus
from app.nlp.qwen_lora_service import DEFAULT_BASE_MODEL, NLPState, QwenLoraIntentService, resolve_adapter_dir

pytestmark = [
    pytest.mark.model,
    pytest.mark.skipif(os.environ.get("RUN_MODEL_TESTS") != "1",
                       reason="real-model test: set RUN_MODEL_TESTS=1 (loads Qwen + LoRA on CPU, about 1-2 minutes)"),
]

ADV = Path(__file__).resolve().parents[2] / "research" / "nlp" / "advanced_llm"


@pytest.fixture(scope="module")
def service():
    svc = QwenLoraIntentService(enabled=True, adapter_dir=resolve_adapter_dir(""), base_model=DEFAULT_BASE_MODEL,
                                local_files_only=False, queue_timeout_seconds=300)
    assert svc.start_background_load() is True
    svc.join_loader(900)
    assert svc.state is NLPState.READY, f"the model did not load (state={svc.state.value}); see the log output"
    return svc


def test_smoke_fuel_message(service):
    result = service.predict("We are running low on fuel. We need to stop soon.")
    assert result.intent == "REFUELING"
    assert result.status in (ParseStatus.EXACT, ParseStatus.EXTRACTED)
    print(f"\nlatency: {result.latency_ms:.0f} ms, raw reply: {result.raw_output!r}")


def test_service_reproduces_the_stored_evaluation_on_a_sample(service):
    rows = []
    for split in ("test", "challenge"):
        path = ADV / "results" / f"lora_predictions_{split}.jsonl"
        if not path.exists():
            pytest.skip(f"missing {path.name}")
        rows += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    failures = [r for r in rows if r["parsed_prediction"] == "PARSE_FAILURE"]          # the invented-label cases
    others = [r for r in rows if r["parsed_prediction"] != "PARSE_FAILURE"]
    sample = failures + [others[int(i * len(others) / 16)] for i in range(16)]        # all failures + 16 spread-out rows

    outcome_mismatches, raw_mismatches = [], []
    for row in sample:
        result = service.predict(row["text"])
        expected = None if row["parsed_prediction"] == "PARSE_FAILURE" else row["parsed_prediction"]
        if result.intent != expected:
            outcome_mismatches.append((row["text"], expected, result.intent, result.raw_output))
        if result.raw_output != row["raw_reply"]:
            raw_mismatches.append((row["raw_reply"], result.raw_output))
    if raw_mismatches:
        warnings.warn(f"{len(raw_mismatches)}/{len(sample)} raw replies differ from the evaluation run "
                      f"(batch-size numerical effects are possible): {raw_mismatches[:3]}")
    assert not outcome_mismatches, f"service disagrees with the stored evaluation: {outcome_mismatches}"
