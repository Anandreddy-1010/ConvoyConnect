"""metrics_utils.py - evaluation/reporting utilities, same pattern as
Phase 3.2/3.3's metrics_utils.py. PARSE_FAILURE is treated as always-wrong."""
import json
from pathlib import Path
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, classification_report, confusion_matrix


def compute_overall_metrics(y_true, y_pred, labels):
    accuracy = accuracy_score(y_true, y_pred)
    macro_p, macro_r, macro_f1, _ = precision_recall_fscore_support(y_true, y_pred, labels=labels, average="macro", zero_division=0)
    _, _, weighted_f1, _ = precision_recall_fscore_support(y_true, y_pred, labels=labels, average="weighted", zero_division=0)
    return {"accuracy": accuracy, "macro_precision": macro_p, "macro_recall": macro_r, "macro_f1": macro_f1, "weighted_f1": weighted_f1}


def compute_per_intent_rows(y_true, y_pred, labels):
    report_dict = classification_report(y_true, y_pred, labels=labels, output_dict=True, zero_division=0)
    return [{"intent": l, "precision": report_dict[l]["precision"], "recall": report_dict[l]["recall"],
             "f1": report_dict[l]["f1-score"], "support": int(report_dict[l]["support"])} for l in labels]


def plot_confusion_matrix(y_true, y_pred, labels, out_path, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    all_labels = list(labels)
    if "PARSE_FAILURE" in set(y_pred) and "PARSE_FAILURE" not in all_labels:
        all_labels = all_labels + ["PARSE_FAILURE"]
    cm = confusion_matrix(y_true, y_pred, labels=all_labels)
    fig, ax = plt.subplots(figsize=(11, 9))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(all_labels))); ax.set_yticks(range(len(all_labels)))
    ax.set_xticklabels(all_labels, rotation=90); ax.set_yticklabels(all_labels)
    ax.set_xlabel("Predicted intent"); ax.set_ylabel("Actual intent"); ax.set_title(title)
    for i in range(len(all_labels)):
        for j in range(len(all_labels)):
            val = cm[i, j]
            if val > 0:
                color = "white" if val > cm.max() / 2 else "black"
                ax.text(j, i, str(val), ha="center", va="center", color=color, fontsize=7)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return cm
