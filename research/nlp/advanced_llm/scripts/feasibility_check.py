"""feasibility_check.py (v2) - measures REAL CPU forward+backward timing for
LoRA fine-tuning using the EXACT training format (shared encoder in
common.py, prompt-masked labels, no truncation), plus a token-length audit.
v1 timed a different, truncated format and 3 steps; v2 uses the real
format and 5 steps and reports a low/mean/high range. Does not train or
save any model."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_config, read_jsonl, write_json, encode_example, make_batch_lists, audit_lengths

HERE = Path(__file__).resolve().parent.parent


def main():
    cfg = load_config()
    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM
        from peft import LoraConfig, get_peft_model
    except ImportError as e:
        print(f"NOT AVAILABLE in this environment: {e}")
        write_json(HERE / "results" / "feasibility_report.json", {"executed": False, "note": f"Required package not available: {e}"})
        sys.exit(0)

    checkpoint = cfg["model_checkpoint"]
    print(f"Loading tokenizer + model: {checkpoint}")
    t0 = time.time()
    tokenizer = AutoTokenizer.from_pretrained(checkpoint)
    model = AutoModelForCausalLM.from_pretrained(checkpoint, torch_dtype=torch.float32)
    t_load = time.time() - t0
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    print(f"Model+tokenizer loaded in {t_load:.1f}s.")

    lora_cfg = cfg["lora"]
    model = get_peft_model(model, LoraConfig(r=lora_cfg["r"], lora_alpha=lora_cfg["lora_alpha"], lora_dropout=lora_cfg["lora_dropout"],
                                               target_modules=lora_cfg["target_modules"], task_type="CAUSAL_LM"))
    trainable, total = model.get_nb_trainable_parameters()
    print(f"LoRA applied. Trainable params: {trainable:,} / {total:,} ({100*trainable/total:.3f}%)")

    train_path = (HERE / "scripts" / Path(cfg["dataset"]["train_path"])).resolve()
    train_records = read_jsonl(train_path)
    print(f"\nAuditing token lengths of all {len(train_records)} training examples in the REAL training format...")
    audit = audit_lengths(tokenizer, train_records, cfg)
    print(f"  tokens per example: min={audit['min_tokens']}  mean={audit['mean_tokens']}  max={audit['max_tokens']}")
    print(f"  answer tokens: min={audit['min_answer_tokens']}  max={audit['max_answer_tokens']}")
    print(f"  examples longer than max_seq_length ({lora_cfg['max_seq_length']}): {audit['n_exceeding_max_seq_length']}")
    if audit["n_exceeding_max_seq_length"] > 0:
        print("  ERROR: some examples exceed max_seq_length -- raise lora.max_seq_length in config.json and re-run.")
        write_json(HERE / "results" / "feasibility_report.json", {"executed": False, "note": "token-length audit failed", "audit": audit})
        sys.exit(1)

    batch_size = lora_cfg["per_device_train_batch_size"]
    n_steps = cfg["feasibility"]["timed_steps"]
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=lora_cfg["learning_rate"])
    model.train()

    print(f"\nRunning {n_steps} timed forward+backward steps, batch_size={batch_size}, REAL format (measurement only)...")
    step_times = []
    for s in range(n_steps):
        chunk = train_records[s * batch_size:(s + 1) * batch_size]
        examples = [encode_example(tokenizer, r[cfg["dataset"]["text_field"]], r[cfg["dataset"]["label_field"]], cfg["intent_labels"]) for r in chunk]
        b = make_batch_lists(examples, tokenizer.pad_token_id)
        enc = {k: torch.tensor(v) for k, v in b.items()}
        t1 = time.time()
        optimizer.zero_grad()
        loss = model(**enc).loss
        loss.backward()
        optimizer.step()
        dt = time.time() - t1
        step_times.append(dt)
        print(f"  Step {s+1}: {dt:.2f}s  (loss on answer tokens only = {loss.item():.4f}, seq_len={enc['input_ids'].shape[1]})")

    steps_per_epoch = max(1, len(train_records) // batch_size)
    total_steps = steps_per_epoch * lora_cfg["num_train_epochs"]
    mean_t, low_t, high_t = sum(step_times) / len(step_times), min(step_times), max(step_times)
    est = lambda t: round(t * total_steps / 60, 1)
    rising = step_times[-1] > 1.3 * step_times[0]

    report = {
        "executed": True, "report_format_version": cfg["feasibility"]["report_format_version"],
        "model_checkpoint": checkpoint, "model_load_time_seconds": round(t_load, 1),
        "trainable_params": trainable, "total_params": total, "token_length_audit": audit,
        "measured_batch_size": batch_size, "measured_step_times_seconds": [round(t, 3) for t in step_times],
        "mean_step_time_seconds": round(mean_t, 3), "train_set_size": len(train_records),
        "steps_per_epoch": steps_per_epoch, "configured_epochs": lora_cfg["num_train_epochs"], "total_training_steps": total_steps,
        "estimated_total_training_time_minutes": est(mean_t),
        "estimated_range_minutes": {"low_fastest_step": est(low_t), "high_slowest_step": est(high_t)},
        "step_times_rising_warning": rising,
        "decision_threshold_minutes": cfg["feasibility"]["decision_threshold_minutes"],
        "recommendation": ("LIKELY FEASIBLE" if est(high_t) <= cfg["feasibility"]["decision_threshold_minutes"] else
                            "BORDERLINE/SLOW -- even the optimistic estimate is near or above the threshold" if est(low_t) > cfg["feasibility"]["decision_threshold_minutes"] else
                            "BORDERLINE -- mean estimate is within the threshold but the slowest-step estimate is not"),
        "extrapolation_caveat": "Linear extrapolation from a few measured steps; real time can differ (thermal throttling, memory pressure, background load such as OneDrive sync).",
    }
    write_json(HERE / "results" / "feasibility_report.json", report)
    print(f"\n=== Feasibility Report (v2) ===")
    print(f"Mean step time: {mean_t:.2f}s   (fastest {low_t:.2f}s, slowest {high_t:.2f}s)")
    print(f"Planned steps: {total_steps} ({steps_per_epoch}/epoch x {lora_cfg['num_train_epochs']} epochs)")
    print(f"ESTIMATED TOTAL: {est(mean_t)} min   (range {est(low_t)} - {est(high_t)} min)")
    if rising:
        print("WARNING: step times are rising across the measured steps (possible thermal throttling) -- the mean may underestimate real time.")
    print(f"Recommendation: {report['recommendation']}")
    print(f"Wrote {HERE / 'results' / 'feasibility_report.json'}")


if __name__ == "__main__":
    main()
