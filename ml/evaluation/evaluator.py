"""
ml/evaluation/evaluator.py - Comprehensive evaluation, inference latency benchmarking,
prediction export, and format-bias diagnostics.
"""

import csv
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import torch
import torch.nn as nn
from sklearn.metrics import classification_report, confusion_matrix, precision_recall_fscore_support
from torch.utils.data import DataLoader
from PIL import Image

from ml.config import (
    CLASS_NAMES,
    CLASS_TO_IDX,
    IDX_TO_CLASS,
    NUM_CLASSES,
    PipelineConfig,
)
from ml.data.dataset import ScoutFireSmokeDataset
from ml.data.transforms import get_eval_transforms
from ml.training.metrics import MetricAccumulator


def compute_test_metrics(
    model: nn.Module,
    test_loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
) -> Dict[str, Any]:
    """
    Evaluates model on the complete test split using deterministic evaluation mode.

    Returns:
        Dictionary with overall metrics (loss, accuracy, macro P/R/F1, weighted F1)
        and per-class breakdowns (P, R, F1, support).
    """
    model.eval()
    all_targets: List[int] = []
    all_preds: List[int] = []
    all_probs: List[np.ndarray] = []
    total_loss = 0.0
    batch_count = 0

    with torch.inference_mode():
        for images, targets in test_loader:
            images = images.to(device)
            targets = targets.to(device)

            logits = model(images)
            loss = criterion(logits, targets)
            total_loss += float(loss.item())
            batch_count += 1

            probs = torch.softmax(logits, dim=-1).cpu().numpy()
            preds = np.argmax(probs, axis=-1)

            all_targets.extend(targets.cpu().numpy().tolist())
            all_preds.extend(preds.tolist())
            all_probs.extend(probs)

    mean_loss = total_loss / max(batch_count, 1)

    y_true = np.array(all_targets, dtype=int)
    y_pred = np.array(all_preds, dtype=int)

    # Class-level metrics
    p_per_class, r_per_class, f1_per_class, support_per_class = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=[0, 1, 2],
        zero_division=0,
    )

    # Macro & Weighted metrics
    p_macro, r_macro, f1_macro, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        average="macro",
        zero_division=0,
    )
    p_weighted, r_weighted, f1_weighted, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        average="weighted",
        zero_division=0,
    )

    accuracy = float(np.mean(y_true == y_pred))
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1, 2]).tolist()

    per_class_dict: Dict[str, Dict[str, float]] = {}
    for idx, class_name in enumerate(CLASS_NAMES):
        per_class_dict[class_name] = {
            "precision": round(float(p_per_class[idx]), 4),
            "recall": round(float(r_per_class[idx]), 4),
            "f1_score": round(float(f1_per_class[idx]), 4),
            "support": int(support_per_class[idx]),
        }

    return {
        "loss": round(mean_loss, 4),
        "accuracy": round(accuracy, 4),
        "macro_precision": round(float(p_macro), 4),
        "macro_recall": round(float(r_macro), 4),
        "macro_f1": round(float(f1_macro), 4),
        "weighted_f1": round(float(f1_weighted), 4),
        "per_class": per_class_dict,
        "confusion_matrix": cm,
        "class_labels": list(CLASS_NAMES),
        "total_test_samples": len(y_true),
    }


def measure_inference_latency(
    model: nn.Module,
    device: torch.device,
    input_shape: Tuple[int, int, int] = (3, 224, 224),
    batch_sizes: Tuple[int, ...] = (1, 16),
    warmup_runs: int = 10,
    measured_runs: int = 50,
) -> Dict[str, Any]:
    """
    Measures CPU inference latency using torch.inference_mode() with warm-up.
    Measures pure model forward-pass time without file loading.
    """
    model.eval()
    latency_results: Dict[str, Any] = {}

    with torch.inference_mode():
        for bs in batch_sizes:
            dummy_input = torch.randn(bs, *input_shape, device=device)

            # Warm-up runs
            for _ in range(warmup_runs):
                _ = model(dummy_input)

            # Measured runs
            timings: List[float] = []
            for _ in range(measured_runs):
                t0 = time.perf_counter()
                _ = model(dummy_input)
                t1 = time.perf_counter()
                timings.append(t1 - t0)

            mean_batch_ms = float(np.mean(timings)) * 1000
            p50_batch_ms = float(np.percentile(timings, 50)) * 1000
            p95_batch_ms = float(np.percentile(timings, 95)) * 1000
            p99_batch_ms = float(np.percentile(timings, 99)) * 1000
            per_image_ms = mean_batch_ms / bs
            throughput_fps = bs / (mean_batch_ms / 1000)

            latency_results[f"batch_{bs}"] = {
                "batch_size": bs,
                "mean_batch_ms": round(mean_batch_ms, 2),
                "p50_batch_ms": round(p50_batch_ms, 2),
                "p95_batch_ms": round(p95_batch_ms, 2),
                "p99_batch_ms": round(p99_batch_ms, 2),
                "per_image_ms": round(per_image_ms, 2),
                "throughput_fps": round(throughput_fps, 2),
            }

    return latency_results


def export_raw_predictions(
    model: nn.Module,
    test_dataset: ScoutFireSmokeDataset,
    device: torch.device,
    output_csv_path: Union[str, Path],
) -> List[Dict[str, Any]]:
    """
    Generates and serializes raw predictions for all items in the test dataset to a CSV file.
    Includes image identifier, ground truth, prediction, class probabilities, and confidence.
    """
    model.eval()
    records: List[Dict[str, Any]] = []

    output_csv_path = Path(output_csv_path)
    output_csv_path.parent.mkdir(parents=True, exist_ok=True)

    with torch.inference_mode():
        for idx in range(len(test_dataset)):
            image_tensor, target = test_dataset[idx]
            image_path_str, _ = test_dataset.samples[idx]
            image_path = Path(image_path_str)
            image_id = image_path.name

            # Add batch dimension
            x = image_tensor.unsqueeze(0).to(device)
            logits = model(x)
            probs = torch.softmax(logits, dim=-1).squeeze(0).cpu().numpy()
            pred_idx = int(np.argmax(probs))
            confidence = float(probs[pred_idx])

            # Detect actual internal raster format from image header
            try:
                with Image.open(image_path) as pil_img:
                    internal_format = pil_img.format or image_path.suffix.lstrip(".").upper()
            except Exception:
                internal_format = image_path.suffix.lstrip(".").upper()

            record = {
                "image_id": image_id,
                "relative_path": str(image_path.name),
                "format": internal_format,
                "extension": image_path.suffix.lower(),
                "ground_truth_idx": int(target),
                "ground_truth_label": IDX_TO_CLASS[int(target)],
                "predicted_idx": pred_idx,
                "predicted_label": IDX_TO_CLASS[pred_idx],
                "confidence": round(confidence, 4),
                "prob_fire": round(float(probs[CLASS_TO_IDX["fire"]]), 4),
                "prob_neutral": round(float(probs[CLASS_TO_IDX["neutral"]]), 4),
                "prob_smoke": round(float(probs[CLASS_TO_IDX["smoke"]]), 4),
                "is_correct": int(target) == pred_idx,
            }
            records.append(record)

    fieldnames = [
        "image_id", "relative_path", "format", "extension", "ground_truth_idx", "ground_truth_label",
        "predicted_idx", "predicted_label", "confidence", "prob_fire", "prob_neutral",
        "prob_smoke", "is_correct"
    ]
    with open(output_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    return records


def analyze_format_bias(predictions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Performs diagnostic analysis of predictions stratified by underlying image format.
    Tests whether neutral performance or error rates differ systematically across formats.
    """
    formats: Dict[str, List[Dict[str, Any]]] = {}
    for r in predictions:
        fmt = r["format"]
        formats.setdefault(fmt, []).append(r)

    analysis: Dict[str, Any] = {}
    for fmt, rows in sorted(formats.items()):
        total = len(rows)
        correct = sum(1 for r in rows if r["is_correct"])
        acc = correct / total if total > 0 else 0.0

        # Class breakdown within format
        gt_counts = {c: sum(1 for r in rows if r["ground_truth_label"] == c) for c in CLASS_NAMES}
        pred_counts = {c: sum(1 for r in rows if r["predicted_label"] == c) for c in CLASS_NAMES}

        analysis[fmt] = {
            "total_images": total,
            "correct_images": correct,
            "accuracy": round(acc, 4),
            "ground_truth_distribution": gt_counts,
            "predicted_distribution": pred_counts,
        }

    # Specifically analyze Neutral class format diversity
    neutral_rows = [r for r in predictions if r["ground_truth_label"] == "neutral"]
    neutral_by_format: Dict[str, Dict[str, Any]] = {}
    for fmt in sorted(set(r["format"] for r in neutral_rows)):
        fmt_neutral = [r for r in neutral_rows if r["format"] == fmt]
        total_n = len(fmt_neutral)
        correct_n = sum(1 for r in fmt_neutral if r["is_correct"])
        neutral_by_format[fmt] = {
            "total_neutral_images": total_n,
            "correct_neutral_images": correct_n,
            "recall": round(correct_n / total_n, 4) if total_n > 0 else 0.0,
        }

    return {
        "overall_by_format": analysis,
        "neutral_class_by_format": neutral_by_format,
        "diagnostic_note": (
            "Diagnostic analysis for format shortcut learning. Neutral class contains multiple formats "
            "(including all TIFF images), while Fire and Smoke are exclusively JPEG. Differences in recall "
            "across formats within Neutral indicate potential texture/encoding shortcut reliance."
        ),
    }
