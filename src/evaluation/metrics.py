from __future__ import annotations

from typing import Dict, List

from sklearn.metrics import accuracy_score, f1_score


def classification_metrics(y_true: List[str], y_pred: List[str], labels: List[str]) -> Dict:
    acc = float(accuracy_score(y_true, y_pred)) if y_true else 0.0
    macro_f1 = float(f1_score(y_true, y_pred, average="macro", labels=labels, zero_division=0)) if y_true else 0.0

    per_class: Dict[str, float] = {}
    if y_true:
        for label in labels:
            score = float(
                f1_score(
                    y_true,
                    y_pred,
                    labels=[label],
                    average="macro",
                    zero_division=0,
                )
            )
            per_class[label] = score

    return {
        "accuracy": acc,
        "f1_macro": macro_f1,
        "per_class_f1": per_class,
    }
