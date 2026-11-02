"""common.py - shared helpers for Phase 3.7 advanced_llm scripts."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent

INTENT_LABELS = [
    "REFUELING", "REST_BREAK", "FOOD_BREAK", "VEHICLE_PROBLEM", "TRAFFIC_DELAY",
    "FALLING_BEHIND", "LOST", "REGROUP_REQUEST", "DESTINATION_CHANGE", "EMERGENCY",
    "STATUS_UPDATE", "GENERAL",
]


def load_config():
    with open(Path(__file__).resolve().parent / "config.json") as f:
        return json.load(f)


def read_jsonl(path):
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def write_jsonl(path, records):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def write_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_prompt(message, labels):
    label_list = ", ".join(labels)
    return (
        "You are classifying a motorcycle group-ride chat message into exactly one intent category.\n"
        f"Categories: {label_list}\n\n"
        f"Message: \"{message}\"\n\n"
        "Reply with ONLY the single category name from the list above, nothing else."
    )


def parse_label_from_response(response_text, labels):
    cleaned = response_text.strip().strip(".").strip('"').upper()
    cleaned = cleaned.replace("-", "_").replace(" ", "_")
    for label in labels:
        if cleaned == label:
            return label
    raw_upper = response_text.upper()
    matches = [label for label in labels if label.replace("_", " ") in raw_upper or label in raw_upper.replace(" ", "_").replace("-", "_")]
    if len(matches) == 1:
        return matches[0]
    return "PARSE_FAILURE"


# ---------------------------------------------------------------------------
# Shared training-example encoding (used by BOTH feasibility_check.py and
# train_lora.py so the feasibility measurement reflects the real training
# format -- v1 of the feasibility check used a different, truncated format).
# ---------------------------------------------------------------------------
def encode_example(tokenizer, message, label, labels):
    """Returns (full_ids, prompt_len). The loss must be computed ONLY on
    the assistant's answer tokens, so prompt_len marks where the answer
    starts. Raises (never silently misaligns) if the prompt tokens are not
    an exact prefix of the full-sequence tokens."""
    user_prompt = build_prompt(message, labels)
    prompt_text = tokenizer.apply_chat_template(
        [{"role": "user", "content": user_prompt}], tokenize=False, add_generation_prompt=True)
    full_text = tokenizer.apply_chat_template(
        [{"role": "user", "content": user_prompt}, {"role": "assistant", "content": label}], tokenize=False)
    if not full_text.startswith(prompt_text):
        raise ValueError("chat template: full text does not start with prompt text")
    prompt_ids = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
    full_ids = tokenizer(full_text, add_special_tokens=False)["input_ids"]
    if full_ids[:len(prompt_ids)] != prompt_ids:
        raise ValueError("tokenization: prompt tokens are not a prefix of full tokens")
    return full_ids, len(prompt_ids)


def make_batch_lists(examples, pad_id):
    """examples: list of (full_ids, prompt_len). Right-pads. Labels are
    -100 (ignored) for prompt tokens and padding, so only the answer
    (+ end-of-turn token) contributes to the loss. Returns python lists."""
    max_len = max(len(ids) for ids, _ in examples)
    input_ids, attention_mask, labels = [], [], []
    for ids, prompt_len in examples:
        pad = max_len - len(ids)
        input_ids.append(ids + [pad_id] * pad)
        attention_mask.append([1] * len(ids) + [0] * pad)
        labels.append([-100] * prompt_len + ids[prompt_len:] + [-100] * pad)
    return {"input_ids": input_ids, "attention_mask": attention_mask, "labels": labels}


def audit_lengths(tokenizer, records, cfg):
    """Token-length statistics over a record list, using the real format."""
    lengths, answer_lengths = [], []
    for r in records:
        ids, plen = encode_example(tokenizer, r[cfg["dataset"]["text_field"]], r[cfg["dataset"]["label_field"]], cfg["intent_labels"])
        lengths.append(len(ids))
        answer_lengths.append(len(ids) - plen)
    return {
        "n": len(lengths), "min_tokens": min(lengths), "mean_tokens": round(sum(lengths) / len(lengths), 1),
        "max_tokens": max(lengths), "min_answer_tokens": min(answer_lengths), "max_answer_tokens": max(answer_lengths),
        "n_exceeding_max_seq_length": sum(1 for l in lengths if l > cfg["lora"]["max_seq_length"]),
    }
