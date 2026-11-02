"""
evaluate_lora.py (v2) - evaluates a LoRA adapter on the original test set and the
naturalistic challenge set. Does not retrain anything.

DEFAULT RUN (no options) behaves as before:
    python evaluate_lora.py
  reads  models/lora_adapter/
  writes results/lora_results.json, figures/confusion_matrix_lora_{test,challenge}.png
  and (new) results/lora_predictions_{test,challenge}.jsonl

SMOKE-TEST / DEBUG RUN (e.g. on the debug adapter):
    python evaluate_lora.py --adapter-dir ../models/_debug_checkpoints/epoch_2/adapter --limit 16 --tag debug
  Any run that uses --limit or a non-default --adapter-dir REQUIRES --tag. A tagged run writes ONLY to
  tag-named files (lora_results_<tag>.json, lora_predictions_<tag>_<split>.jsonl,
  confusion_matrix_lora_<tag>_<split>.png), which can never equal a default output name, so a debug
  run cannot overwrite real results. Metrics from a --limit run are plumbing checks, NOT valid results.
"""
import argparse, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_config, read_jsonl, write_json, write_jsonl, build_prompt, parse_label_from_response
from metrics_utils import compute_overall_metrics, compute_per_intent_rows, plot_confusion_matrix

HERE = Path(__file__).resolve().parent.parent
DEFAULT_ADAPTER_DIR = HERE / "models" / "lora_adapter"
TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")


# ---------- output naming: tagged runs can never collide with default names ----------
def results_path(tag):
    return HERE / "results" / (f"lora_results_{tag}.json" if tag else "lora_results.json")


def predictions_path(tag, split):
    return HERE / "results" / f"lora_predictions_{tag + '_' if tag else ''}{split}.jsonl"


def figure_path(tag, split):
    return HERE / "figures" / f"confusion_matrix_lora_{tag + '_' if tag else ''}{split}.png"


# ---------- argument rules ----------
def validate_args(tag, limit, adapter_dir):
    """Returns an error string, or None if the combination is allowed."""
    if tag is not None and not TAG_RE.match(tag):
        return "--tag must be 1-40 characters: letters, digits, '_' or '-' (starting with a letter or digit)."
    if limit is not None and limit < 1:
        return "--limit must be a positive integer."
    non_default = limit is not None or (
        adapter_dir is not None and Path(adapter_dir).resolve() != DEFAULT_ADAPTER_DIR.resolve())
    if non_default and tag is None:
        return ("--limit or a non-default --adapter-dir requires --tag, so debug outputs go to separate "
                "tag-named files and can never overwrite the real results.")
    return None


def select_subset(records, limit):
    """Deterministic, evenly spaced subset (the data files are ordered by intent, so taking the first N
    would only test one or two intents)."""
    n = len(records)
    if limit is None or limit >= n:
        return records
    return [records[int(i * n / limit)] for i in range(limit)]


def resolve_dataset_paths(cfg):
    return [("test", (HERE / "scripts" / Path(cfg["dataset"]["test_path"])).resolve()),
            ("challenge", (HERE / "scripts" / Path(cfg["dataset"]["challenge_path"])).resolve())]


def find_missing_datasets(dataset_paths):
    return [(name, path) for name, path in dataset_paths if not path.exists()]


def evaluate_on_split(model, tokenizer, device, records, cfg, split_name, tag=None):
    import torch
    labels = cfg["intent_labels"]
    text_field = cfg["dataset"]["text_field"]
    label_field = cfg["dataset"]["label_field"]
    batch_size = cfg["zero_shot"]["batch_size"]
    max_new_tokens = cfg["zero_shot"]["max_new_tokens"]
    y_true = [r[label_field] for r in records]
    y_pred = []
    raw_replies = []
    print(f"Running LoRA-fine-tuned inference on {len(records)} examples ({split_name})...")
    t_start = time.time()
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        prompts = []
        for r in batch:
            messages = [{"role": "user", "content": build_prompt(r[text_field], labels)}]
            prompts.append(tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True))
        enc = tokenizer(prompts, return_tensors="pt", padding=True, truncation=True, max_length=512).to(device)
        with torch.no_grad():
            out = model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False,
                                   pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id)
        for j in range(len(batch)):
            gen_tokens = out[j][enc["input_ids"].shape[1]:]
            response = tokenizer.decode(gen_tokens, skip_special_tokens=True)
            raw_replies.append(response)
            y_pred.append(parse_label_from_response(response, labels))
        print(f"  {min(i+batch_size,len(records))}/{len(records)}", end="\r")
    elapsed = time.time() - t_start
    print(f"\n  Done in {elapsed:.1f}s")
    parse_failures = sum(1 for p in y_pred if p == "PARSE_FAILURE")
    overall = compute_overall_metrics(y_true, y_pred, labels)
    per_intent = compute_per_intent_rows(y_true, y_pred, labels)
    (HERE / "figures").mkdir(exist_ok=True)
    plot_confusion_matrix(y_true, y_pred, labels, figure_path(tag, split_name),
                            f"LoRA fine-tuned {cfg['model_checkpoint']} -- {split_name} set (real predictions)"
                            + (f" [DEBUG:{tag}]" if tag else ""))
    rows = [{"id": r.get("id", f"{split_name}_{k}"), "text": r[text_field], "true_label": y_true[k],
             "raw_reply": raw_replies[k], "parsed_prediction": y_pred[k]} for k, r in enumerate(records)]
    result = {"split": split_name, "n_examples": len(records), "metrics": overall, "per_intent": per_intent,
              "parse_failure_count": parse_failures, "parse_failure_rate": parse_failures / len(records),
              "elapsed_seconds": round(elapsed, 1)}
    return result, rows


def main():
    ap = argparse.ArgumentParser(description="Evaluate a LoRA adapter (see module docstring).")
    ap.add_argument("--adapter-dir", default=None, help="adapter folder (default: models/lora_adapter)")
    ap.add_argument("--limit", type=int, default=None, help="evaluate only N evenly spaced examples per split (debug)")
    ap.add_argument("--tag", default=None, help="label for a debug run; outputs go to tag-named files")
    args = ap.parse_args()

    err = validate_args(args.tag, args.limit, args.adapter_dir)
    if err:
        print(f"ERROR: {err}")
        sys.exit(2)

    tag = args.tag
    adapter_dir = Path(args.adapter_dir).resolve() if args.adapter_dir else DEFAULT_ADAPTER_DIR
    res_path = results_path(tag)
    cfg = load_config()

    if tag:
        print("=" * 78)
        print(f"DEBUG RUN [{tag}]: outputs go ONLY to tag-named files; real results are not touched.")
        if args.limit:
            print(f"  --limit {args.limit}: metrics from this run are plumbing checks, NOT valid results.")
        print("=" * 78)

    if not adapter_dir.is_dir() or not any(adapter_dir.iterdir()):
        print(f"No adapter found at {adapter_dir}. " + ("" if tag else "Run train_lora.py first."))
        write_json(res_path, {"executed": False, "note": f"No adapter found at {adapter_dir}."})
        return

    # Warn about missing datasets BEFORE the (slow) model load.
    dataset_paths = resolve_dataset_paths(cfg)
    missing = find_missing_datasets(dataset_paths)
    for name, path in missing:
        print(f"WARNING: {name} dataset NOT FOUND at {path}")
        print(f"         The {name} split will NOT be evaluated and will be missing from the results.")

    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM
        from peft import PeftModel
    except ImportError as e:
        print(f"NOT AVAILABLE in this environment: {e}")
        write_json(res_path, {"executed": False, "note": f"Required package not available: {e}"})
        return

    checkpoint = cfg["model_checkpoint"]
    # Final adapter folders include the tokenizer; per-epoch checkpoint adapters do not (the tokenizer is the
    # unmodified base tokenizer), so fall back to the base model's tokenizer in that case.
    has_tokenizer = (adapter_dir / "tokenizer_config.json").exists()
    tokenizer_source = str(adapter_dir) if has_tokenizer else checkpoint
    print(f"Loading base model {checkpoint} + LoRA adapter from {adapter_dir}")
    print(f"Tokenizer source: {'adapter folder' if has_tokenizer else 'base model (adapter folder has no tokenizer files)'}")
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_source)
    base_model = AutoModelForCausalLM.from_pretrained(checkpoint, torch_dtype=torch.float32)
    model = PeftModel.from_pretrained(base_model, str(adapter_dir))
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "left"  # REQUIRED for correct batched generation with decoder-only models
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device); model.eval()

    results = {"executed": True, "model_checkpoint": checkpoint, "mode": "lora_fine_tuned",
               "run_info": {"tag": tag, "debug": bool(tag), "limit": args.limit, "adapter_dir": str(adapter_dir),
                            "tokenizer_source": "adapter" if has_tokenizer else "base_model"},
               "missing_splits": [name for name, _ in missing]}
    if tag:
        results["debug_note"] = "DEBUG RUN: not a valid evaluation result."

    for split_name, path in dataset_paths:
        if (split_name, path) in missing:
            continue
        records = select_subset(read_jsonl(path), args.limit)
        result, rows = evaluate_on_split(model, tokenizer, device, records, cfg, split_name, tag)
        results[split_name] = result
        write_jsonl(predictions_path(tag, split_name), rows)
        print(f"  {split_name}: accuracy={result['metrics']['accuracy']:.4f}  macro_f1={result['metrics']['macro_f1']:.4f}  "
              f"parse_failures={result['parse_failure_count']}/{result['n_examples']}")
        print(f"  Wrote per-example predictions: {predictions_path(tag, split_name)}")

    write_json(res_path, results)
    print(f"\nWrote {res_path}")
    if missing:
        print(f"WARNING: results are INCOMPLETE -- missing split(s): {', '.join(n for n, _ in missing)}")


if __name__ == "__main__":
    main()
