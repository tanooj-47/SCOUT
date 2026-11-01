"""
ml/tests/test_evaluation.py - Unit tests for evaluation, latency measurement,
prediction export, and format bias analysis.
"""

import csv
import json
from pathlib import Path
import numpy as np
import pytest
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from ml.config import CLASS_NAMES, NUM_CLASSES
from ml.evaluation.evaluator import (
    analyze_format_bias,
    compute_test_metrics,
    measure_inference_latency,
)


class DummyModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.fc = nn.Linear(3 * 224 * 224, NUM_CLASSES)

    def forward(self, x):
        x = x.view(x.size(0), -1)
        return self.fc(x)


def test_compute_test_metrics_canonical_order_and_bounds():
    torch.manual_seed(42)
    model = DummyModel()
    criterion = nn.CrossEntropyLoss()

    dummy_x = torch.randn(30, 3, 224, 224)
    dummy_y = torch.tensor([0, 1, 2] * 10, dtype=torch.long)
    dataset = TensorDataset(dummy_x, dummy_y)
    loader = DataLoader(dataset, batch_size=10, shuffle=False)

    metrics = compute_test_metrics(model, loader, criterion, torch.device("cpu"))

    assert "loss" in metrics
    assert "accuracy" in metrics
    assert "macro_f1" in metrics
    assert "per_class" in metrics
    assert "confusion_matrix" in metrics

    assert 0.0 <= metrics["accuracy"] <= 1.0
    assert 0.0 <= metrics["macro_f1"] <= 1.0

    # Verify per-class labels match canonical names exactly
    assert list(metrics["per_class"].keys()) == list(CLASS_NAMES)
    for cls in CLASS_NAMES:
        assert "precision" in metrics["per_class"][cls]
        assert "recall" in metrics["per_class"][cls]
        assert "f1_score" in metrics["per_class"][cls]
        assert "support" in metrics["per_class"][cls]
        assert metrics["per_class"][cls]["support"] == 10

    cm = np.array(metrics["confusion_matrix"])
    assert cm.shape == (3, 3)
    assert cm.sum() == 30


def test_measure_inference_latency_structure():
    model = DummyModel()
    device = torch.device("cpu")
    latency = measure_inference_latency(
        model, device, batch_sizes=(1, 4), warmup_runs=2, measured_runs=5
    )

    assert "batch_1" in latency
    assert "batch_4" in latency
    assert latency["batch_1"]["per_image_ms"] > 0
    assert latency["batch_4"]["throughput_fps"] > 0


def test_analyze_format_bias_grouping():
    mock_predictions = [
        {"format": ".jpg", "ground_truth_label": "fire", "predicted_label": "fire", "is_correct": True},
        {"format": ".jpg", "ground_truth_label": "neutral", "predicted_label": "neutral", "is_correct": True},
        {"format": ".tif", "ground_truth_label": "neutral", "predicted_label": "smoke", "is_correct": False},
        {"format": ".png", "ground_truth_label": "neutral", "predicted_label": "neutral", "is_correct": True},
    ]

    analysis = analyze_format_bias(mock_predictions)
    assert "overall_by_format" in analysis
    assert "neutral_class_by_format" in analysis

    assert ".jpg" in analysis["overall_by_format"]
    assert ".tif" in analysis["overall_by_format"]
    assert ".png" in analysis["overall_by_format"]

    assert analysis["neutral_class_by_format"][".tif"]["recall"] == 0.0
    assert analysis["neutral_class_by_format"][".jpg"]["recall"] == 1.0


def test_confusion_matrix_row_column_invariants():
    """Verify that confusion matrix rows sum to ground-truth class support."""
    y_true = np.array([0, 0, 0, 1, 1, 2])
    y_pred = np.array([0, 1, 2, 1, 1, 0])
    from sklearn.metrics import confusion_matrix
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1, 2])
    # Row 0 (True 0): 3 samples
    assert cm[0].sum() == 3
    # Row 1 (True 1): 2 samples
    assert cm[1].sum() == 2
    # Row 2 (True 2): 1 sample
    assert cm[2].sum() == 1


def test_checkpoint_artifact_loading_and_parameter_invariants():
    """Verify saved best checkpoint loads cleanly and matches architecture parameter counts."""
    ckpt_path = Path("artifacts/checkpoints/baseline_cnn_best.pt")
    if not ckpt_path.exists():
        pytest.skip("Baseline CNN checkpoint has not been trained yet.")

    from ml.models.baseline_cnn import BaselineCNN
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    assert "model_state_dict" in ckpt
    assert ckpt["model_architecture"] == "baseline_cnn"

    model = BaselineCNN(num_classes=NUM_CLASSES)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()

    total_params = sum(p.numel() for p in model.parameters())
    assert total_params == 405539

    with torch.inference_mode():
        dummy = torch.randn(2, 3, 224, 224)
        logits = model(dummy)
        assert logits.shape == (2, NUM_CLASSES)
        assert torch.isfinite(logits).all()


def test_model_comparison_artifact_schema():
    """Verify that the model comparison artifact conforms to expected structure."""
    comp_path = Path("artifacts/metrics/model_comparison.json")
    if not comp_path.exists():
        pytest.skip("Model comparison artifact does not exist yet.")

    with open(comp_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "metrics_comparison" in data
    assert "selection" in data
    assert data["selection"]["selected_model"] in ("baseline_cnn", "mobilenet_v3_small")
    assert "test_accuracy" in data["metrics_comparison"]
    assert "macro_f1" in data["metrics_comparison"]

