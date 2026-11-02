# ConvoyConnect Phase 3.7 -- Advanced Instruction-Tuned LLM (LoRA)

**Status: PIPELINE COMPLETE, NOTHING EXECUTED YET.** This sandbox has no
internet access and cannot install torch/transformers/peft. All scripts
are written, syntax-verified, and their safety gates verified working.
Real execution must happen on your machine.

## Research question
Can a small instruction-tuned LLM (zero-shot, and optionally LoRA
fine-tuned) match or beat the existing DistilBERT baseline -- especially
on the naturalistic challenge set, where DistilBERT (74.58%) and TF-IDF
(67.92%) both degrade substantially from their near-perfect in-distribution scores?

## What's reused, unmodified
- `../dataset/{train,validation,test}.jsonl` (Phase 3.1)
- `../comparison/challenging_set/challenge_eval.jsonl` (Phase 3.4)
- Reference numbers from Phase 3.2/3.3/3.4 result files

**Not touched:** frontend/, backend/, Phase 3.5 gps_fusion/, Phase 3.6 GPS code.

## Candidate model
`Qwen/Qwen2.5-0.5B-Instruct`. QLoRA is NOT attempted (bitsandbytes has
poor/no CPU support on Windows) -- standard 16-bit LoRA via `peft` is
used instead, gated on a real feasibility measurement.

## Run order
```bash
cd research/nlp/advanced_llm/scripts
pip install -r ../requirements.txt

python3 feasibility_check.py      # 1. ALWAYS first - measures real CPU step time
python3 zero_shot_eval.py         # 2. ALWAYS runs - no training needed
python3 train_lora.py             # 3. ONLY after reviewing feasibility numbers (refuses without report)
python3 evaluate_lora.py          # 4. Only produces output if step 3 completed
python3 build_comparison_report.py # 5. Combines everything honestly
```

## Safety gates (verified working)
- `train_lora.py` refuses (exit 1) if `results/feasibility_report.json` is missing.
- `evaluate_lora.py` reports "NOT EXECUTED" (no fabrication) if no adapter exists.
- All scripts detect missing torch/transformers/peft and exit cleanly.

## Evaluation
Every arm is evaluated on BOTH the original test (180) and challenge (240)
sets: accuracy, macro P/R/F1, weighted F1, per-intent, confusion matrix.
`PARSE_FAILURE` (output not mappable to a valid label) counts as wrong and is
reported as its own rate.

## Limitations (documented in advance)
- CPU-only LoRA will likely take far longer than DistilBERT's ~9 minutes.
- QLoRA not attempted (genuine scope reduction, not an oversight).
- Zero-shot results depend heavily on prompt wording; one reasonable prompt used, not tuned.
- All data is synthetic/template-generated or a single author's naturalistic approximation.

## Results
**Not yet available** -- see `reports/phase3_7_comparison.md` (updates when re-run).

---

## UPDATE (v3): LoRA training configuration, checkpointing, and why 2 epochs

This section supersedes any earlier text in this README about epochs or loss.

### Why exactly 2 epochs (a documented compute limitation)
The v2 feasibility run (real training format, 5 timed steps) measured ~9.6 s/step on this CPU
(range 7.96-11.29 s). For the 840-example training set at batch size 4 (210 steps/epoch):

| Epochs | Steps | Estimated time (mean; fastest-slowest step) |
|---|---|---|
| 3 | 630 | 100.8 min (83.5 - 118.6) |
| **2 (chosen)** | **420** | **67.2 min (55.7 - 79.0)** |

2 epochs was chosen **because of CPU computing limits**, and it was fixed **before any LoRA
result existed**; it was not selected using test-set or challenge-set performance. It is a
compute-driven limitation, not a tuned hyperparameter. A model trained for fewer epochs than
is ideal may under-perform; any LoRA result must be read with that caveat.

### Loss and sequence-length fixes (made before any training)
- Loss is computed on the assistant's **answer tokens only** (prompt tokens masked with -100).
- `max_seq_length` raised 128 -> 256: a token audit on the real format found examples of
  121-141 tokens (mean 130.2), so the old limit would have truncated many examples.
- Generation scripts use **left padding** (required for correct batched decoding).

### Checkpointing and resume (epoch-level)
- A checkpoint (LoRA adapter + optimizer state + RNG state + training state) is written after
  each completed epoch to `models/checkpoints/epoch_N/`.
- If training is interrupted, re-running `python train_lora.py` resumes automatically from the
  last completed epoch. An interrupted epoch is **re-run from its beginning** (at most ~33 min
  lost); mid-epoch state is deliberately not saved.
- Each epoch's example order depends only on (seed, epoch), so a resumed run sees exactly the
  same batches as an uninterrupted one.
- Checkpoints are written to a temp directory and renamed, with a pointer file updated last, so
  a crash during saving cannot leave a half-written checkpoint that looks valid.
- Resume is **refused** if the saved configuration (epochs, learning rate, LoRA settings, seed,
  data size, ...) differs from the current one; use `--fresh` to discard checkpoints.
- Checkpoints are for crash recovery only. They are **not** used to pick the "best" epoch.

### Verification
- `python test_resume_logic.py` (no torch needed): 10 checks of the control flow using a fake
  deterministic model: crash mid-epoch, crash during a save, config mismatch, completed-run
  resume, etc. An interrupted+resumed run ends in exactly the same state as an uninterrupted run.
- The torch/peft calls (adapter save/load, optimizer/RNG restore) cannot be tested without torch.
  They are verified by a ~2-minute **real-model smoke test**:
  ```
  python train_lora.py --debug-steps 3 --debug-stop-after-epoch 1   # trains 3 steps, checkpoints, stops
  python train_lora.py --debug-steps 3                              # must print "RESUMING: 1 of 2 epochs..."
  ```
  Debug mode writes only to `models/_debug_checkpoints/` and `results/_debug_training_log.json`.

### Evaluation is unchanged
`zero_shot_eval.py`, `evaluate_lora.py`, `metrics_utils.py` and the evaluation procedure
(accuracy, macro P/R/F1, weighted F1, per-intent, confusion matrix, PARSE_FAILURE counted wrong)
are not modified by this update.
