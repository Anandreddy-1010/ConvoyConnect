"""Parser / prompt / label tests. Pure Python: no model, no FastAPI."""
import importlib.util
import json
from pathlib import Path

import pytest

from app.nlp.intent_parsing import (
    INTENT_LABELS, MAX_NEW_TOKENS, ParseResult, ParseStatus, build_prompt, parse_model_output,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ADV = REPO_ROOT / "research" / "nlp" / "advanced_llm"


def _need(path: Path):
    if not path.exists():
        pytest.skip(f"research file not present: {path.relative_to(REPO_ROOT)}")
    return path


# ------------------------------------------------------------------ labels / prompt stay identical to training
def test_labels_match_training_config_exactly():
    cfg = json.loads(_need(ADV / "scripts" / "config.json").read_text(encoding="utf-8"))
    assert list(INTENT_LABELS) == cfg["intent_labels"], "labels or their order drifted from scripts/config.json"
    assert len(INTENT_LABELS) == 12 and len(set(INTENT_LABELS)) == 12
    assert MAX_NEW_TOKENS == cfg["zero_shot"]["max_new_tokens"]


def test_prompt_is_identical_to_the_training_prompt():
    spec = importlib.util.spec_from_file_location("research_common", _need(ADV / "scripts" / "common.py"))
    research = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(research)
    assert list(INTENT_LABELS) == research.INTENT_LABELS
    for message in ["We are running low on fuel. We need to stop soon.", 'He said "stop" now', "two\nlines", "  padded  ", "x"]:
        assert build_prompt(message) == research.build_prompt(message, research.INTENT_LABELS), message


# ------------------------------------------------------------------ parser behaviour
CASES = [
    # raw model reply                              expected intent   expected status
    ("REFUELING",                                  "REFUELING",      ParseStatus.EXACT),
    ("refueling",                                  "REFUELING",      ParseStatus.EXACT),
    ("  REST_BREAK \n",                            "REST_BREAK",     ParseStatus.EXACT),
    ('"FOOD_BREAK"',                               "FOOD_BREAK",     ParseStatus.EXACT),
    ("`LOST`",                                     "LOST",           ParseStatus.EXACT),
    ("**EMERGENCY**",                              "EMERGENCY",      ParseStatus.EXACT),
    ("REFUELING.",                                 "REFUELING",      ParseStatus.EXACT),
    ("REFUELING\n\nThe rider is low on fuel.",     "REFUELING",      ParseStatus.EXTRACTED),
    ("TRAFFIC_DELAY - heavy traffic ahead",        "TRAFFIC_DELAY",  ParseStatus.EXTRACTED),
    ("LOST: the rider missed a turn",              "LOST",           ParseStatus.EXTRACTED),
    ("REFUELING_STATION",                          None,             ParseStatus.INVALID_LABEL),   # not a prefix match
    ("REFUEL",                                     None,             ParseStatus.INVALID_LABEL),
    ("NESTED",                                     None,             ParseStatus.INVALID_LABEL),   # real invented label
    ("ENERGY_LEVEL",                               None,             ParseStatus.INVALID_LABEL),   # real invented label
    ("The category is LOST",                       None,             ParseStatus.INVALID_LABEL),   # must START with a label
    ("Rest break",                                 None,             ParseStatus.INVALID_LABEL),
    ("- REFUELING",                                None,             ParseStatus.INVALID_LABEL),
    ("I am not sure",                              None,             ParseStatus.INVALID_LABEL),
    ("",                                           None,             ParseStatus.EMPTY_OUTPUT),
    ("   \n\t ",                                   None,             ParseStatus.EMPTY_OUTPUT),
    ("TRAFFIC_DELAY or FALLING_BEHIND",            None,             ParseStatus.AMBIGUOUS_OUTPUT),
    ("REFUELING. Not a REST_BREAK.",               None,             ParseStatus.AMBIGUOUS_OUTPUT),
    ("EMERGENCY\nGENERAL",                         None,             ParseStatus.AMBIGUOUS_OUTPUT),
    ("REFUELING. Refueling is needed.",            "REFUELING",      ParseStatus.EXTRACTED),       # repeats the SAME label: fine
]


def test_parser_cases():
    for raw, expected_intent, expected_status in CASES:
        got = parse_model_output(raw)
        assert (got.intent, got.status) == (expected_intent, expected_status), f"{raw!r} -> {got}"
        assert got.succeeded == (expected_intent is not None), raw


def test_every_label_round_trips_exactly():
    for label in INTENT_LABELS:
        assert parse_model_output(label) == ParseResult(label, ParseStatus.EXACT)


def test_failed_parse_never_falls_back_to_a_default_label():
    for raw, expected_intent, _ in CASES:
        if expected_intent is None:
            result = parse_model_output(raw)
            assert result.intent is None and result.intent != "GENERAL" and not result.succeeded


def test_parse_result_has_no_confidence():
    assert not hasattr(parse_model_output("REFUELING"), "confidence")


def test_only_success_statuses_count_as_success():
    assert set(ParseStatus.SUCCESS) == {ParseStatus.EXACT, ParseStatus.EXTRACTED}
    assert ParseResult("LOST", ParseStatus.INVALID_LABEL).succeeded is False   # inconsistent combos never "succeed"
    assert ParseResult(None, ParseStatus.EXACT).succeeded is False


# ------------------------------------------------------------------ the REAL model replies from the Phase 3.7 evaluation
def test_parser_agrees_with_all_real_evaluation_replies():
    rows = []
    for split in ("test", "challenge"):
        path = _need(ADV / "results" / f"lora_predictions_{split}.jsonl")
        rows += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 420, f"expected 180 + 240 real replies, found {len(rows)}"

    mismatches, failures = [], 0
    for row in rows:
        parsed = parse_model_output(row["raw_reply"])
        stored = row["parsed_prediction"]
        expected = None if stored == "PARSE_FAILURE" else stored
        failures += parsed.intent is None
        if parsed.intent != expected:
            mismatches.append((row["raw_reply"], stored, parsed))
    assert not mismatches, f"API parser disagrees with the stored evaluation on {len(mismatches)} real replies: {mismatches[:3]}"
    assert failures == sum(1 for r in rows if r["parsed_prediction"] == "PARSE_FAILURE")
