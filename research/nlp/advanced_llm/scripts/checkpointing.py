"""
checkpointing.py - epoch-level checkpoint / resume bookkeeping for LoRA
training. Pure Python (no torch): the model/optimizer save callbacks are
injected, so this control flow can be unit-tested without a GPU/torch.

POLICY
- A checkpoint is written ONLY after an epoch fully completes.
- If training is interrupted mid-epoch, the next run resumes from the last
  completed epoch and RE-RUNS the interrupted epoch from its beginning
  (at most one epoch of work is lost; ~33 min at the measured speed).
- Each epoch's example order is derived from (seed, epoch), independent of
  history, so an interrupted+resumed run sees exactly the same batches as an
  uninterrupted run.
- Checkpoints are written to a temp directory and renamed into place, then a
  pointer file (latest.json) is updated last. A crash mid-save therefore can
  never produce a half-written checkpoint that looks complete.
- A checkpoint is only reused if its config fingerprint matches the current
  config exactly; otherwise resume is REFUSED (never silently mixed).
"""
import json
import os
import random
import shutil
import time
from pathlib import Path

FORMAT_VERSION = 1


class CheckpointMismatch(Exception):
    pass


def config_fingerprint(cfg, n_train, debug_steps=None):
    l = cfg["lora"]
    return {
        "format_version": FORMAT_VERSION,
        "model_checkpoint": cfg["model_checkpoint"],
        "random_state": cfg["random_state"],
        "epochs": l["num_train_epochs"],
        "batch_size": l["per_device_train_batch_size"],
        "learning_rate": l["learning_rate"],
        "r": l["r"], "lora_alpha": l["lora_alpha"], "lora_dropout": l["lora_dropout"],
        "target_modules": l["target_modules"], "max_seq_length": l["max_seq_length"],
        "n_train": n_train, "loss_masking": "answer_only", "debug_steps": debug_steps,
    }


def epoch_order(n_examples, seed, epoch, limit=None):
    """Deterministic shuffle for a given 0-indexed epoch."""
    rng = random.Random(seed * 1000 + epoch)
    idx = list(range(n_examples))
    rng.shuffle(idx)
    return idx[:limit] if limit else idx


def atomic_write_json(path, obj):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_resume_state(ckpt_dir, fingerprint):
    """Returns the saved state dict (with 'epoch_dir') or None if there is no
    checkpoint. Raises CheckpointMismatch on a fingerprint mismatch or a
    pointer to a missing checkpoint (never silently restarts)."""
    ckpt_dir = Path(ckpt_dir)
    latest = ckpt_dir / "latest.json"
    if not latest.exists():
        return None
    pointer = json.loads(latest.read_text(encoding="utf-8"))
    epoch_dir = ckpt_dir / pointer["epoch_dir"]
    state_path = epoch_dir / "state.json"
    if not state_path.exists():
        raise CheckpointMismatch(
            f"latest.json points to {epoch_dir.name}, but its state.json is missing. "
            f"Re-run with --fresh to discard checkpoints and start over.")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state["fingerprint"] != fingerprint:
        diffs = {k: (state["fingerprint"].get(k), fingerprint.get(k))
                 for k in set(fingerprint) | set(state["fingerprint"])
                 if state["fingerprint"].get(k) != fingerprint.get(k)}
        raise CheckpointMismatch(
            f"checkpoint was made with a different configuration (saved vs current): {diffs}. "
            f"Re-run with --fresh to discard it.")
    state["epoch_dir"] = str(epoch_dir)
    return state


def save_epoch_checkpoint(ckpt_dir, epochs_completed, state, save_model_fn, save_optimizer_fn):
    ckpt_dir = Path(ckpt_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    final_dir = ckpt_dir / f"epoch_{epochs_completed}"
    tmp_dir = ckpt_dir / f"epoch_{epochs_completed}.tmp"
    if final_dir.exists():
        raise FileExistsError(f"refusing to overwrite completed checkpoint {final_dir}")
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)          # leftover from a crash during a previous save
    tmp_dir.mkdir()
    save_model_fn(tmp_dir / "adapter")
    save_optimizer_fn(tmp_dir / "optimizer_and_rng.pt")
    atomic_write_json(tmp_dir / "state.json", state)   # written last inside the dir
    os.replace(tmp_dir, final_dir)                      # directory appears atomically
    atomic_write_json(ckpt_dir / "latest.json",
                      {"epoch_dir": final_dir.name, "epochs_completed": epochs_completed})


def run_epochs(n_examples, cfg, fingerprint, ckpt_dir, step_fn, save_model_fn, save_optimizer_fn,
               resume_state=None, limit_examples_per_epoch=None, stop_after_epoch=None,
               log=print, log_every=20):
    """Runs the epoch loop. step_fn(list_of_example_indices) -> float loss.
    Returns (state, status) with status 'completed' or 'stopped_for_debug'."""
    total_epochs = cfg["lora"]["num_train_epochs"]
    bs = cfg["lora"]["per_device_train_batch_size"]
    seed = cfg["random_state"]

    if resume_state is not None:
        state = {k: v for k, v in resume_state.items() if k != "epoch_dir"}
        state["resume_history"] = list(state.get("resume_history", [])) + [
            {"resumed_after_epochs_completed": state["epochs_completed"],
             "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}]
        log(f"RESUMING: {state['epochs_completed']} of {total_epochs} epochs already complete "
            f"(global step {state['global_step']}). Continuing with epoch {state['epochs_completed'] + 1}.")
    else:
        state = {"fingerprint": fingerprint, "epochs_completed": 0, "global_step": 0, "losses": [],
                 "epoch_mean_losses": [], "epoch_seconds": [], "accumulated_train_seconds": 0.0,
                 "resume_history": []}

    if state["epochs_completed"] >= total_epochs:
        log("All epochs already complete in the checkpoint; nothing left to train.")
        return state, "completed"

    for epoch in range(state["epochs_completed"], total_epochs):
        order = epoch_order(n_examples, seed, epoch, limit_examples_per_epoch)
        t0 = time.time()
        epoch_losses = []
        step_in_run = state["global_step"]
        for i in range(0, len(order), bs):
            loss = step_fn(order[i:i + bs])
            epoch_losses.append(loss)
            step_in_run += 1
            if step_in_run % log_every == 0:
                log(f"  epoch {epoch + 1}/{total_epochs} step {step_in_run} loss={loss:.4f} "
                    f"epoch_elapsed={(time.time() - t0) / 60:.1f}min")
        dt = time.time() - t0
        # state is updated ONLY after the whole epoch finished
        state["epochs_completed"] = epoch + 1
        state["global_step"] = step_in_run
        state["losses"].extend(epoch_losses)
        state["epoch_mean_losses"].append(sum(epoch_losses) / len(epoch_losses))
        state["epoch_seconds"].append(round(dt, 1))
        state["accumulated_train_seconds"] += dt
        log(f"Epoch {epoch + 1}/{total_epochs} complete: mean loss {state['epoch_mean_losses'][-1]:.4f}, "
            f"{dt / 60:.1f} min. Saving checkpoint...")
        save_epoch_checkpoint(ckpt_dir, epoch + 1, state, save_model_fn, save_optimizer_fn)
        log(f"Checkpoint saved: epoch_{epoch + 1}")
        if stop_after_epoch is not None and epoch + 1 == stop_after_epoch and epoch + 1 < total_epochs:
            log(f"DEBUG: stopping cleanly after epoch {epoch + 1} to simulate an interruption.")
            return state, "stopped_for_debug"
    return state, "completed"
