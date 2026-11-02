"""
train_lora.py (v3) - LoRA fine-tuning, answer-token-only loss, with
epoch-level checkpointing and resume (see checkpointing.py for the policy).

Usage:
  python train_lora.py                    # train (auto-resumes from a valid checkpoint if one exists)
  python train_lora.py --fresh            # discard existing checkpoints and start over
  python train_lora.py --debug-steps 3 --debug-stop-after-epoch 1
  python train_lora.py --debug-steps 3    # re-run: should RESUME at epoch 2 (smoke test, ~2 min)

Debug mode writes ONLY to models/_debug_checkpoints and results/_debug_training_log.json;
it never writes models/lora_adapter or results/lora_training_log.json.

REFUSES TO RUN unless a v2 feasibility report exists.
2 epochs is a CPU-compute-driven choice -- see config.json "epochs_rationale".
"""
import argparse, json, shutil, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_config, read_jsonl, write_json, encode_example, make_batch_lists, audit_lengths
from checkpointing import config_fingerprint, load_resume_state, run_epochs, CheckpointMismatch

HERE = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true", help="delete existing checkpoints for this mode and start over")
    ap.add_argument("--debug-steps", type=int, default=None, help="smoke test: only N optimizer steps per epoch")
    ap.add_argument("--debug-stop-after-epoch", type=int, default=None, help="smoke test: stop cleanly after this epoch")
    args = ap.parse_args()
    debug = args.debug_steps is not None

    cfg = load_config()
    lora_cfg = cfg["lora"]
    bs, epochs = lora_cfg["per_device_train_batch_size"], lora_cfg["num_train_epochs"]

    # ---------- gate: a valid v2 feasibility report must exist ----------
    fp = HERE / "results" / "feasibility_report.json"
    if not fp.exists():
        print("REFUSING TO START: results/feasibility_report.json does not exist. Run feasibility_check.py first."); sys.exit(1)
    feas = json.load(open(fp))
    if not feas.get("executed"):
        print(f"REFUSING TO START: feasibility check did not complete. Note: {feas.get('note')}"); sys.exit(1)
    if feas.get("report_format_version") != cfg["feasibility"]["report_format_version"]:
        print("REFUSING TO START: feasibility_report.json is from an older check version. Re-run feasibility_check.py."); sys.exit(1)

    # Estimate for the CONFIGURED epoch count, recomputed from the MEASURED per-step times
    # (the report itself is not modified).
    steps_total = (feas["train_set_size"] // bs) * epochs
    times = feas["measured_step_times_seconds"]
    est = lambda t: round(t * steps_total / 60, 1)
    print("=== Time estimate for the configured run (from measured step times) ===")
    print(f"  {epochs} epochs x {feas['train_set_size'] // bs} steps = {steps_total} steps")
    print(f"  mean {est(feas['mean_step_time_seconds'])} min   (fastest-step {est(min(times))} - slowest-step {est(max(times))} min)")
    if feas.get("configured_epochs") != epochs:
        print(f"  (note: the feasibility report was made with epochs={feas.get('configured_epochs')}; per-step timing is unchanged, estimate recomputed)")
    print(f"  Why {epochs} epochs: {cfg['epochs_rationale']}\n")

    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM
        from peft import LoraConfig, get_peft_model, PeftModel
    except ImportError as e:
        print(f"NOT AVAILABLE in this environment: {e}")
        write_json(HERE / "results" / ("_debug_training_log.json" if debug else "lora_training_log.json"),
                   {"executed": False, "note": f"Required package not available: {e}"})
        return

    torch.manual_seed(cfg["random_state"])
    ckpt_dir = HERE / "models" / ("_debug_checkpoints" if debug else "checkpoints")
    if args.fresh and ckpt_dir.exists():
        shutil.rmtree(ckpt_dir)
        print(f"--fresh: removed {ckpt_dir}")

    checkpoint = cfg["model_checkpoint"]
    tokenizer = AutoTokenizer.from_pretrained(checkpoint)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"          # training uses right padding (generation scripts use left)

    train_records = read_jsonl((HERE / "scripts" / Path(cfg["dataset"]["train_path"])).resolve())
    audit = audit_lengths(tokenizer, train_records, cfg)
    print(f"Token audit: {audit}")
    if audit["n_exceeding_max_seq_length"] > 0:
        print("REFUSING TO START: some examples exceed max_seq_length; the answer could be truncated away."); sys.exit(1)
    encoded = [encode_example(tokenizer, r[cfg["dataset"]["text_field"]], r[cfg["dataset"]["label_field"]], cfg["intent_labels"])
               for r in train_records]

    # ---------- resume or fresh model ----------
    fingerprint = config_fingerprint(cfg, len(encoded), debug_steps=args.debug_steps)
    try:
        resume_state = load_resume_state(ckpt_dir, fingerprint)
    except CheckpointMismatch as e:
        print(f"REFUSING TO RESUME: {e}"); sys.exit(1)

    base = AutoModelForCausalLM.from_pretrained(checkpoint, torch_dtype=torch.float32)
    if resume_state is not None:
        epoch_dir = Path(resume_state["epoch_dir"])
        model = PeftModel.from_pretrained(base, str(epoch_dir / "adapter"), is_trainable=True)
        print(f"Loaded LoRA adapter from checkpoint {epoch_dir.name}")
    else:
        model = get_peft_model(base, LoraConfig(r=lora_cfg["r"], lora_alpha=lora_cfg["lora_alpha"], lora_dropout=lora_cfg["lora_dropout"],
                                                  target_modules=lora_cfg["target_modules"], task_type="CAUSAL_LM"))
    model.print_trainable_parameters()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device); model.train()
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=lora_cfg["learning_rate"])
    if resume_state is not None:
        blob = torch.load(epoch_dir / "optimizer_and_rng.pt", map_location="cpu", weights_only=True)
        optimizer.load_state_dict(blob["optimizer"])
        torch.set_rng_state(blob["torch_rng_state"])       # restores the LoRA-dropout RNG stream
        if blob.get("cuda_rng_state_all") is not None and torch.cuda.is_available():
            torch.cuda.set_rng_state_all(blob["cuda_rng_state_all"])
        print("Restored optimizer state and RNG state from checkpoint.")

    # ---------- callbacks handed to the (unit-tested) epoch loop ----------
    def step_fn(indices):
        b = make_batch_lists([encoded[j] for j in indices], tokenizer.pad_token_id)
        enc = {k: torch.tensor(v).to(device) for k, v in b.items()}
        optimizer.zero_grad()
        loss = model(**enc).loss
        loss.backward()
        optimizer.step()
        return loss.item()

    def save_model_fn(path):
        model.save_pretrained(str(path))

    def save_optimizer_fn(path):
        torch.save({"optimizer": optimizer.state_dict(), "torch_rng_state": torch.get_rng_state(),
                    "cuda_rng_state_all": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None}, str(path))

    state, status = run_epochs(
        len(encoded), cfg, fingerprint, ckpt_dir, step_fn, save_model_fn, save_optimizer_fn, resume_state=resume_state,
        limit_examples_per_epoch=(args.debug_steps * bs if debug else None),
        stop_after_epoch=args.debug_stop_after_epoch)

    if status == "stopped_for_debug":
        print(f"\nDEBUG smoke test: stopped after epoch {state['epochs_completed']}. Re-run the same command WITHOUT "
              f"--debug-stop-after-epoch to verify it resumes at epoch {state['epochs_completed'] + 1}.")
        return

    log = {
        "executed": True, "debug_mode": debug, "checkpoint": checkpoint, "epochs": epochs, "epochs_rationale": cfg["epochs_rationale"],
        "total_steps": state["global_step"], "final_loss": state["losses"][-1],
        "epoch_mean_losses": state["epoch_mean_losses"], "epoch_seconds": state["epoch_seconds"],
        "loss_curve_sample": state["losses"][::max(1, len(state["losses"]) // 50)],
        "accumulated_train_minutes": round(state["accumulated_train_seconds"] / 60, 1),
        "resumed": len(state["resume_history"]) > 0, "resume_history": state["resume_history"],
        "feasibility_estimate_minutes_for_configured_epochs": est(feas["mean_step_time_seconds"]),
        "loss_masking": "answer tokens only", "trained_on": "Phase 3.1 train split only (840 examples)"}
    if debug:
        write_json(HERE / "results" / "_debug_training_log.json", log)
        print("\nDEBUG smoke test complete (resume path verified). Real adapter NOT written. Delete models/_debug_checkpoints when done.")
        return

    adapter_dir = HERE / "models" / "lora_adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(adapter_dir)); tokenizer.save_pretrained(str(adapter_dir))
    write_json(HERE / "results" / "lora_training_log.json", log)
    print(f"\nTraining complete: {log['accumulated_train_minutes']} min of training "
          f"(estimate {log['feasibility_estimate_minutes_for_configured_epochs']} min). Saved adapter to {adapter_dir}")


if __name__ == "__main__":
    main()
