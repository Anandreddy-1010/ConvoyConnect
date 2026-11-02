# Phase 3.7 -- Advanced LLM Comparison Report

Phase 3.2/3.3/3.4 numbers are transcribed from those phases' own real result files. Zero-shot/LoRA cells read NOT EXECUTED until their scripts have actually run -- never estimated.

## Original test set (180 examples)

| System | Accuracy | Macro F1 |
|---|---|---|
| TF-IDF + Logistic Regression | 0.9889 | 0.9888 |
| DistilBERT (fine-tuned) | 1.0000 | 1.0000 |
| Qwen2.5-0.5B-Instruct (zero-shot) | 0.3722 | 0.3717 |
| Qwen2.5-0.5B-Instruct — LoRA, 2 epochs (compute-limited) | 0.9778 | 0.9776 |

## Naturalistic challenge set (240 examples)

| System | Accuracy | Macro F1 |
|---|---|---|
| TF-IDF + Logistic Regression | 0.6792 | 0.6713 |
| DistilBERT (fine-tuned) | 0.7458 | 0.7376 |
| Qwen2.5-0.5B-Instruct (zero-shot) | 0.3292 | 0.3060 |
| Qwen2.5-0.5B-Instruct — LoRA, 2 epochs (compute-limited) | 0.7625 | 0.7718 |

Zero-shot parse failures on test: 8/180 (4.4%) -- counted as wrong, never guessed.
Zero-shot parse failures on challenge: 12/240 (5.0%) -- counted as wrong, never guessed.

LoRA (2 epochs, compute-limited) parse failures on test: 0/180 (0.0%) -- counted as wrong, never guessed.
LoRA (2 epochs, compute-limited) parse failures on challenge: 4/240 (1.7%) -- counted as wrong, never guessed.

## Status

- Zero-shot evaluation: EXECUTED
- LoRA fine-tuning: EXECUTED