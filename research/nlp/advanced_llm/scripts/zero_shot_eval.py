"""zero_shot_eval.py - evaluates the candidate LLM in ZERO-SHOT mode
(no fine-tuning) on BOTH the original test set and the naturalistic
challenge set. Always runs regardless of LoRA feasibility."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_config, read_jsonl, write_json, build_prompt, parse_label_from_response
from metrics_utils import compute_overall_metrics, compute_per_intent_rows, plot_confusion_matrix

HERE = Path(__file__).resolve().parent.parent


def evaluate_on_split(model, tokenizer, device, records, cfg, split_name, figures_dir):
    import torch
    labels = cfg["intent_labels"]
    text_field = cfg["dataset"]["text_field"]
    label_field = cfg["dataset"]["label_field"]
    batch_size = cfg["zero_shot"]["batch_size"]
    max_new_tokens = cfg["zero_shot"]["max_new_tokens"]
    y_true = [r[label_field] for r in records]
    y_pred = []
    raw_responses = []
    print(f"Running zero-shot inference on {len(records)} examples ({split_name})...")
    t_start = time.time()
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        prompts = []
        for r in batch:
            user_prompt = build_prompt(r[text_field], labels)
            messages = [{"role": "user", "content": user_prompt}]
            chat_text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            prompts.append(chat_text)
        enc = tokenizer(prompts, return_tensors="pt", padding=True, truncation=True, max_length=512).to(device)
        with torch.no_grad():
            out = model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=cfg["zero_shot"]["do_sample"],
                                   pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id)
        for j in range(len(batch)):
            gen_tokens = out[j][enc["input_ids"].shape[1]:]
            response = tokenizer.decode(gen_tokens, skip_special_tokens=True)
            raw_responses.append(response)
            y_pred.append(parse_label_from_response(response, labels))
        print(f"  {min(i+batch_size,len(records))}/{len(records)}", end="\r")
    elapsed = time.time() - t_start
    print(f"\n  Done in {elapsed:.1f}s ({elapsed/len(records):.2f}s/example)")
    parse_failures = sum(1 for p in y_pred if p == "PARSE_FAILURE")
    overall = compute_overall_metrics(y_true, y_pred, labels)
    per_intent = compute_per_intent_rows(y_true, y_pred, labels)
    plot_confusion_matrix(y_true, y_pred, labels, figures_dir / f"confusion_matrix_zero_shot_{split_name}.png",
                            f"Zero-Shot {cfg['model_checkpoint']} -- {split_name} set (real predictions)")
    return {"split": split_name, "n_examples": len(records), "metrics": overall, "per_intent": per_intent,
            "parse_failure_count": parse_failures, "parse_failure_rate": parse_failures / len(records),
            "elapsed_seconds": round(elapsed, 1), "sample_raw_responses": raw_responses[:10]}


def main():
    cfg = load_config()
    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM
    except ImportError as e:
        print(f"NOT AVAILABLE in this environment: {e}")
        write_json(HERE / "results" / "zero_shot_results.json", {"executed": False, "note": f"Required package not available: {e}"})
        return

    checkpoint = cfg["model_checkpoint"]
    print(f"Loading tokenizer + model: {checkpoint}")
    tokenizer = AutoTokenizer.from_pretrained(checkpoint)
    model = AutoModelForCausalLM.from_pretrained(checkpoint, torch_dtype=torch.float32)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "left"  # REQUIRED for correct batched generation with decoder-only models
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device); model.eval()
    print(f"Model loaded. Device: {device}")

    test_path = (HERE / "scripts" / Path(cfg["dataset"]["test_path"])).resolve()
    challenge_path = (HERE / "scripts" / Path(cfg["dataset"]["challenge_path"])).resolve()
    figures_dir = HERE / "figures"; figures_dir.mkdir(exist_ok=True)
    results = {"executed": True, "model_checkpoint": checkpoint, "mode": "zero_shot"}

    if test_path.exists():
        test_records = read_jsonl(test_path)
        results["test"] = evaluate_on_split(model, tokenizer, device, test_records, cfg, "test", figures_dir)
        print(f"  Test set: accuracy={results['test']['metrics']['accuracy']:.4f}  macro_f1={results['test']['metrics']['macro_f1']:.4f}  parse_failures={results['test']['parse_failure_count']}/{results['test']['n_examples']}")
    else:
        print(f"WARNING: test set not found at {test_path}")

    if challenge_path.exists():
        challenge_records = read_jsonl(challenge_path)
        results["challenge"] = evaluate_on_split(model, tokenizer, device, challenge_records, cfg, "challenge", figures_dir)
        print(f"  Challenge set: accuracy={results['challenge']['metrics']['accuracy']:.4f}  macro_f1={results['challenge']['metrics']['macro_f1']:.4f}  parse_failures={results['challenge']['parse_failure_count']}/{results['challenge']['n_examples']}")
    else:
        print(f"WARNING: challenge set not found at {challenge_path}")

    write_json(HERE / "results" / "zero_shot_results.json", results)
    print(f"\nWrote {HERE / 'results' / 'zero_shot_results.json'}")


if __name__ == "__main__":
    main()
