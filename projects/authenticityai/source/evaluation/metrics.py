"""Binary, calibration, grouped, and bootstrap evaluation metrics."""

from __future__ import annotations

import math
import random
from collections import defaultdict


def _validate(scores, labels):
    scores = [max(0.0, min(1.0, float(value))) for value in scores]
    labels = [1 if value in (1, True, "ai") else 0 for value in labels]
    if not scores or len(scores) != len(labels):
        raise ValueError("scores and labels must be non-empty and equally sized")
    return scores, labels


def confusion(scores, labels, threshold=0.5):
    scores, labels = _validate(scores, labels)
    predictions = [int(score >= threshold) for score in scores]
    return {
        "tp": sum(p == y == 1 for p, y in zip(predictions, labels)),
        "tn": sum(p == y == 0 for p, y in zip(predictions, labels)),
        "fp": sum(p == 1 and y == 0 for p, y in zip(predictions, labels)),
        "fn": sum(p == 0 and y == 1 for p, y in zip(predictions, labels)),
    }


def _safe(numerator, denominator):
    return numerator / denominator if denominator else 0.0


def roc_auc(scores, labels):
    scores, labels = _validate(scores, labels)
    positives = sum(labels)
    negatives = len(labels) - positives
    if not positives or not negatives:
        return None
    ordered = sorted(zip(scores, labels), key=lambda row: row[0])
    rank_sum = 0.0
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][0] == ordered[index][0]:
            end += 1
        average_rank = (index + 1 + end) / 2.0
        rank_sum += average_rank * sum(label for _score, label in ordered[index:end])
        index = end
    return (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)


def pr_auc(scores, labels):
    scores, labels = _validate(scores, labels)
    positives = sum(labels)
    if not positives:
        return None
    ordered = sorted(zip(scores, labels), reverse=True)
    tp = fp = 0
    previous_recall = 0.0
    area = 0.0
    for _score, label in ordered:
        tp += label
        fp += 1 - label
        recall = tp / positives
        precision = tp / (tp + fp)
        area += (recall - previous_recall) * precision
        previous_recall = recall
    return area


def expected_calibration_error(scores, labels, bins=10):
    scores, labels = _validate(scores, labels)
    total = len(scores)
    result = 0.0
    reliability = []
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        selected = [position for position, score in enumerate(scores) if low <= score < high or (index == bins - 1 and score == 1.0)]
        if not selected:
            reliability.append({"low": low, "high": high, "count": 0, "mean_confidence": None, "observed_rate": None})
            continue
        confidence = sum(scores[position] for position in selected) / len(selected)
        observed = sum(labels[position] for position in selected) / len(selected)
        result += len(selected) / total * abs(confidence - observed)
        reliability.append({"low": low, "high": high, "count": len(selected), "mean_confidence": confidence, "observed_rate": observed})
    return result, reliability


def binary_metrics(scores, labels, threshold=0.5):
    scores, labels = _validate(scores, labels)
    matrix = confusion(scores, labels, threshold)
    tp, tn, fp, fn = matrix["tp"], matrix["tn"], matrix["fp"], matrix["fn"]
    precision = _safe(tp, tp + fp)
    recall = _safe(tp, tp + fn)
    specificity = _safe(tn, tn + fp)
    ece, reliability = expected_calibration_error(scores, labels)
    return {
        "sample_count": len(scores),
        "accuracy": _safe(tp + tn, len(scores)),
        "balanced_accuracy": (recall + specificity) / 2.0,
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "f1": _safe(2 * precision * recall, precision + recall),
        "false_positive_rate": _safe(fp, fp + tn),
        "false_negative_rate": _safe(fn, fn + tp),
        "roc_auc": roc_auc(scores, labels),
        "pr_auc": pr_auc(scores, labels),
        "brier_score": sum((score - label) ** 2 for score, label in zip(scores, labels)) / len(scores),
        "expected_calibration_error": ece,
        "confusion_matrix": matrix,
        "reliability_diagram": reliability,
        "threshold": threshold,
    }


def bootstrap_confidence_intervals(scores, labels, *, groups=None, iterations=500, seed=2026, confidence=0.95):
    scores, labels = _validate(scores, labels)
    rng = random.Random(seed)
    if groups is None:
        units = [[index] for index in range(len(scores))]
    else:
        if len(groups) != len(scores):
            raise ValueError("groups must match score count")
        by_group = defaultdict(list)
        for index, group in enumerate(groups):
            by_group[str(group)].append(index)
        units = list(by_group.values())
    values = defaultdict(list)
    for _ in range(int(iterations)):
        selected = [rng.choice(units) for _unit in units]
        indices = [index for unit in selected for index in unit]
        sample_labels = [labels[index] for index in indices]
        if len(set(sample_labels)) < 2:
            continue
        result = binary_metrics([scores[index] for index in indices], sample_labels)
        for name in ("accuracy", "balanced_accuracy", "precision", "recall", "specificity", "f1", "false_positive_rate", "false_negative_rate", "roc_auc", "pr_auc", "brier_score", "expected_calibration_error"):
            if result[name] is not None:
                values[name].append(result[name])
    alpha = (1.0 - confidence) / 2.0
    output = {}
    for name, samples in values.items():
        samples.sort()
        if not samples:
            continue
        low = samples[max(0, math.floor(alpha * (len(samples) - 1)))]
        high = samples[min(len(samples) - 1, math.ceil((1 - alpha) * (len(samples) - 1)))]
        output[name] = {"low": low, "high": high, "confidence": confidence, "successful_iterations": len(samples)}
    return output


def grouped_metrics(rows, field, threshold=0.5):
    grouped = defaultdict(list)
    for row in rows:
        grouped[str(row.get(field) or "unknown")].append(row)
    return {
        name: binary_metrics(
            [row["score"] for row in members],
            [row["label"] for row in members],
            threshold,
        )
        for name, members in grouped.items()
        if len({row["label"] for row in members}) == 2
    }


def confidence_band_metrics(rows, threshold=0.5, bands=((0.0, 0.5), (0.5, 0.75), (0.75, 0.9), (0.9, 1.01))):
    output = {}
    for low, high in bands:
        members = [row for row in rows if low <= float(row.get("confidence", 0.0)) < high]
        summary = {
            "count": len(members),
            "accuracy": _safe(sum(row.get("correct", False) for row in members), len(members)),
        }
        if members and len({row["label"] for row in members}) == 2:
            summary.update(binary_metrics([row["score"] for row in members], [row["label"] for row in members], threshold))
        output[f"{low:.2f}-{min(high, 1.0):.2f}"] = summary
    return output
