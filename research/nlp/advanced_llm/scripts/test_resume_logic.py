"""test_resume_logic.py - verifies checkpointing.py's control flow with a
fake, deterministic 'model' (no torch). The fake model's end state is a hash
of every batch it was trained on, IN ORDER, so any skipped / repeated /
leaked batch changes the final state. Run: python3 test_resume_logic.py"""
import hashlib, json, shutil, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from checkpointing import (config_fingerprint, load_resume_state, run_epochs, CheckpointMismatch,
                           epoch_order, save_epoch_checkpoint)

CFG = {"model_checkpoint": "fake", "random_state": 42,
       "lora": {"num_train_epochs": 2, "per_device_train_batch_size": 4, "learning_rate": 2e-4, "r": 8,
                "lora_alpha": 16, "lora_dropout": 0.05, "target_modules": ["q_proj"], "max_seq_length": 256}}
N = 840                                     # same size/batch as the real run -> 210 steps/epoch
FP = config_fingerprint(CFG, N)


class FakeModel:
    def __init__(self): self.digest, self.batches = "init", []
    def step(self, idx):
        self.batches.append(list(idx))
        self.digest = hashlib.sha256((self.digest + json.dumps(idx)).encode()).hexdigest()
        return 1.0 / (1 + len(self.batches))            # deterministic fake loss
    def save(self, d): d.mkdir(); (d / "m.json").write_text(json.dumps({"digest": self.digest}))
    def load(self, d): self.digest = json.loads((d / "m.json").read_text())["digest"]


def harness(model, ckpt, resume_state=None, boom_at_global_step=None, save_boom=False, **kw):
    counter = {"n": resume_state["global_step"] if resume_state else 0}
    def step_fn(idx):
        counter["n"] += 1
        if boom_at_global_step is not None and counter["n"] == boom_at_global_step:
            raise RuntimeError("simulated crash / laptop sleep / power loss")
        return model.step(idx)
    def save_model(d):
        if save_boom: raise RuntimeError("simulated crash DURING checkpoint save")
        model.save(d)
    return run_epochs(N, CFG, FP, ckpt, step_fn, save_model, lambda p: Path(p).write_text("opt"),
                      resume_state=resume_state, log=lambda *_: None, **kw)


def resume(model, ckpt, **kw):
    rs = load_resume_state(ckpt, FP)
    if rs is not None: model.load(Path(rs["epoch_dir"]) / "adapter")
    return rs, harness(model, ckpt, resume_state=rs, **kw)


tmp = Path(tempfile.mkdtemp())
try:
    # --- A. uninterrupted reference run ---
    ref = FakeModel(); st, status = harness(ref, tmp / "A")
    assert status == "completed" and st["epochs_completed"] == 2 and st["global_step"] == 420
    assert len(ref.batches) == 420
    print("A. uninterrupted run: 420 steps (210/epoch), 2 epochs, checkpoints epoch_1 + epoch_2 ... PASS")

    # --- B. crash in the MIDDLE of epoch 2 (global step 300), then resume ---
    m1 = FakeModel()
    try: harness(m1, tmp / "B", boom_at_global_step=300); raise SystemExit("expected crash")
    except RuntimeError: pass
    assert json.loads((tmp / "B" / "latest.json").read_text())["epochs_completed"] == 1
    m2 = FakeModel()                                     # brand-new process
    rs, (st2, status2) = resume(m2, tmp / "B")
    assert rs["epochs_completed"] == 1 and rs["global_step"] == 210
    assert status2 == "completed" and st2["epochs_completed"] == 2 and st2["global_step"] == 420
    assert m2.digest == ref.digest, "resumed end state must equal uninterrupted end state"
    ep2_ref = ref.batches[210:]; assert m2.batches == ep2_ref, "resumed run must replay epoch 2 batches identically"
    assert len(st2["resume_history"]) == 1 and len(st2["losses"]) == 420
    print("B. crash mid-epoch-2 -> resume from epoch_1, replays epoch 2 identically, end state == uninterrupted ... PASS")

    # --- C. crash mid-epoch-1: nothing saved, fresh start, still identical ---
    m3 = FakeModel()
    try: harness(m3, tmp / "C", boom_at_global_step=50); raise SystemExit("expected crash")
    except RuntimeError: pass
    assert not (tmp / "C" / "latest.json").exists()
    m4 = FakeModel(); rs, (st4, _) = resume(m4, tmp / "C")
    assert rs is None and m4.digest == ref.digest
    print("C. crash mid-epoch-1 -> no checkpoint, clean restart, end state == uninterrupted ... PASS")

    # --- D. crash DURING the epoch-2 checkpoint save: epoch_1 must remain the valid resume point ---
    m5 = FakeModel(); calls = {"n": 0}
    def flaky_save_harness():
        counter = {"n": 0}
        def step_fn(idx): return m5.step(idx)
        def save_model(d):
            calls["n"] += 1
            if calls["n"] == 2: raise RuntimeError("crash during epoch-2 save")
            m5.save(d)
        return run_epochs(N, CFG, FP, tmp / "D", step_fn, save_model, lambda p: Path(p).write_text("opt"), log=lambda *_: None)
    try: flaky_save_harness(); raise SystemExit("expected crash")
    except RuntimeError: pass
    assert json.loads((tmp / "D" / "latest.json").read_text())["epochs_completed"] == 1
    assert (tmp / "D" / "epoch_2.tmp").exists() and not (tmp / "D" / "epoch_2").exists()
    m6 = FakeModel(); rs, (st6, s6) = resume(m6, tmp / "D")
    assert rs["epochs_completed"] == 1 and s6 == "completed" and m6.digest == ref.digest
    assert not (tmp / "D" / "epoch_2.tmp").exists() and (tmp / "D" / "epoch_2").exists()
    print("D. crash during epoch-2 save -> half-written dir ignored+cleaned, resumes from epoch_1 ... PASS")

    # --- E. already complete: resuming does no extra training ---
    m7 = FakeModel(); rs, (st7, s7) = resume(m7, tmp / "A")
    assert rs["epochs_completed"] == 2 and s7 == "completed" and m7.batches == [] and m7.digest == ref.digest
    print("E. resume of a fully-finished run -> trains 0 extra steps, loads final weights ... PASS")

    # --- F. config mismatch is refused, never silently mixed ---
    CFG2 = json.loads(json.dumps(CFG)); CFG2["lora"]["learning_rate"] = 1e-3
    try: load_resume_state(tmp / "A", config_fingerprint(CFG2, N)); raise SystemExit("expected refusal")
    except CheckpointMismatch as e: assert "learning_rate" in str(e)
    CFG3 = json.loads(json.dumps(CFG)); CFG3["lora"]["num_train_epochs"] = 3
    try: load_resume_state(tmp / "A", config_fingerprint(CFG3, N)); raise SystemExit("expected refusal")
    except CheckpointMismatch: pass
    print("F. changed learning rate / epoch count -> resume refused with explanation ... PASS")

    # --- G. pointer to a missing checkpoint is an error, not a silent restart ---
    shutil.copytree(tmp / "A", tmp / "G"); shutil.rmtree(tmp / "G" / "epoch_2")
    try: load_resume_state(tmp / "G", FP); raise SystemExit("expected error")
    except CheckpointMismatch: pass
    print("G. latest.json -> missing checkpoint dir -> loud error (no silent restart) ... PASS")

    # --- H. never overwrite a completed checkpoint ---
    try: save_epoch_checkpoint(tmp / "A", 1, {}, lambda d: d.mkdir(), lambda p: None); raise SystemExit("expected error")
    except FileExistsError: pass
    print("H. refuses to overwrite a completed checkpoint ... PASS")

    # --- I. debug smoke-test mode: 3 steps/epoch, stop after epoch 1, then resume to finish ---
    dbg_fp = config_fingerprint(CFG, N, debug_steps=3)
    def dbg(model, rs=None, stop=None):
        return run_epochs(N, CFG, dbg_fp, tmp / "I", lambda idx: model.step(idx), lambda d: model.save(d),
                          lambda p: Path(p).write_text("o"), resume_state=rs, limit_examples_per_epoch=12,
                          stop_after_epoch=stop, log=lambda *_: None)
    d1 = FakeModel(); st, s = dbg(d1, stop=1); assert s == "stopped_for_debug" and st["global_step"] == 3
    d2 = FakeModel(); rs = load_resume_state(tmp / "I", dbg_fp); d2.load(Path(rs["epoch_dir"]) / "adapter")
    st, s = dbg(d2, rs=rs); assert s == "completed" and st["global_step"] == 6
    print("I. debug mode (3 steps/epoch): stop after epoch 1, resume, finish at 6 steps ... PASS")

    # --- J. epoch order is a pure function of (seed, epoch) and each epoch is a full permutation ---
    assert epoch_order(N, 42, 0) == epoch_order(N, 42, 0) and epoch_order(N, 42, 0) != epoch_order(N, 42, 1)
    assert sorted(epoch_order(N, 42, 1)) == list(range(N))
    print("J. epoch ordering deterministic per (seed, epoch); every epoch covers all 840 examples ... PASS")

    print("\nALL 10 CHECKS PASSED (control-flow logic only; torch/peft save+load calls are verified by the real-model debug smoke test)")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
