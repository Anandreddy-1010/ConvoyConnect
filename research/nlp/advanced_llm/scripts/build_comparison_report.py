"""build_comparison_report.py - combines zero-shot, LoRA (if any), and
existing Phase 3.2/3.3/3.4 baseline numbers into one comparison report.
Never fabricates a number -- anything not run is reported NOT EXECUTED."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import read_json

HERE = Path(__file__).resolve().parent.parent

# Written with a \u2014 escape so this source file stays pure ASCII (no dependence on how an editor saves it).
LORA_LABEL = "Qwen2.5-0.5B-Instruct \u2014 LoRA, 2 epochs (compute-limited)"

REFERENCE = {
    "tfidf_logreg": {"test_accuracy": 0.9889, "test_macro_f1": 0.9888, "challenge_accuracy": 0.6792, "challenge_macro_f1": 0.6713},
    "distilbert": {"test_accuracy": 1.0000, "test_macro_f1": 1.0000, "challenge_accuracy": 0.7458, "challenge_macro_f1": 0.7376},
}


def fmt(results, split, key):
    if results is None or not results.get("executed"):
        return "NOT EXECUTED"
    split_data = results.get(split)
    if split_data is None:
        return "N/A (split not found)"
    return f"{split_data['metrics'][key]:.4f}"


def main():
    results_dir = HERE / "results"
    zs_path, lora_path = results_dir / "zero_shot_results.json", results_dir / "lora_results.json"
    zero_shot = read_json(zs_path) if zs_path.exists() else None
    lora = read_json(lora_path) if lora_path.exists() else None

    md = ["# Phase 3.7 -- Advanced LLM Comparison Report\n",
          "Phase 3.2/3.3/3.4 numbers are transcribed from those phases' own real result files. "
          "Zero-shot/LoRA cells read NOT EXECUTED until their scripts have actually run -- never estimated.\n",
          "## Original test set (180 examples)\n", "| System | Accuracy | Macro F1 |", "|---|---|---|",
          f"| TF-IDF + Logistic Regression | {REFERENCE['tfidf_logreg']['test_accuracy']:.4f} | {REFERENCE['tfidf_logreg']['test_macro_f1']:.4f} |",
          f"| DistilBERT (fine-tuned) | {REFERENCE['distilbert']['test_accuracy']:.4f} | {REFERENCE['distilbert']['test_macro_f1']:.4f} |",
          f"| Qwen2.5-0.5B-Instruct (zero-shot) | {fmt(zero_shot,'test','accuracy')} | {fmt(zero_shot,'test','macro_f1')} |",
          f"| {LORA_LABEL} | {fmt(lora,'test','accuracy')} | {fmt(lora,'test','macro_f1')} |", "",
          "## Naturalistic challenge set (240 examples)\n", "| System | Accuracy | Macro F1 |", "|---|---|---|",
          f"| TF-IDF + Logistic Regression | {REFERENCE['tfidf_logreg']['challenge_accuracy']:.4f} | {REFERENCE['tfidf_logreg']['challenge_macro_f1']:.4f} |",
          f"| DistilBERT (fine-tuned) | {REFERENCE['distilbert']['challenge_accuracy']:.4f} | {REFERENCE['distilbert']['challenge_macro_f1']:.4f} |",
          f"| Qwen2.5-0.5B-Instruct (zero-shot) | {fmt(zero_shot,'challenge','accuracy')} | {fmt(zero_shot,'challenge','macro_f1')} |",
          f"| {LORA_LABEL} | {fmt(lora,'challenge','accuracy')} | {fmt(lora,'challenge','macro_f1')} |", ""]

    if zero_shot and zero_shot.get("executed"):
        for split in ["test", "challenge"]:
            if split in zero_shot:
                pf, n = zero_shot[split]["parse_failure_count"], zero_shot[split]["n_examples"]
                md.append(f"Zero-shot parse failures on {split}: {pf}/{n} ({100*pf/n:.1f}%) -- counted as wrong, never guessed.")
        md.append("")

    if lora and lora.get("executed"):
        for split in ["test", "challenge"]:
            if split in lora:
                pf, n = lora[split]["parse_failure_count"], lora[split]["n_examples"]
                md.append(f"LoRA (2 epochs, compute-limited) parse failures on {split}: {pf}/{n} ({100*pf/n:.1f}%) -- counted as wrong, never guessed.")
        md.append("")

    md += ["## Status\n",
           f"- Zero-shot evaluation: {'EXECUTED' if zero_shot and zero_shot.get('executed') else 'NOT YET EXECUTED'}",
           f"- LoRA fine-tuning: {'EXECUTED' if lora and lora.get('executed') else 'NOT YET EXECUTED'}"]
    (HERE / "reports" / "phase3_7_comparison.md").write_text("\n".join(md), encoding="utf-8-sig")
    print("Wrote reports/phase3_7_comparison.md")


if __name__ == "__main__":
    main()
