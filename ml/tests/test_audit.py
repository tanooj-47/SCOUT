"""
ml/tests/test_audit.py - Verification tests for Phase 6 dataset integrity,
leakage audit, and normalization invariants.
"""

import csv
import json
from pathlib import Path
import pytest

AUDIT_DIR = Path("artifacts/audits/m07_phase6")
PREDICTIONS_CSV = Path("artifacts/predictions/baseline_cnn_predictions.csv")


def test_audit_artifacts_exist():
    """Verify that all Phase 6 audit artifacts were created in artifacts/audits/m07_phase6/."""
    expected_files = [
        "dataset_distribution.json",
        "duplicate_audit.json",
        "format_bias_audit.json",
        "normalized_evaluation.json",
        "prediction_error_analysis.json",
        "confidence_analysis.json",
        "audit_summary.json",
        "prediction_changes.csv",
    ]
    for filename in expected_files:
        fpath = AUDIT_DIR / filename
        assert fpath.exists(), f"Missing audit artifact: {fpath}"
        assert fpath.stat().st_size > 0, f"Empty audit artifact: {fpath}"


def test_exact_duplicates_is_zero():
    """Verify that the duplicate audit found zero cross-split or intra-split exact duplicates."""
    dup_path = AUDIT_DIR / "duplicate_audit.json"
    with open(dup_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert len(data["exact_duplicate_groups"]) == 0
    assert len(data["cross_split_duplicates"]) == 0
    assert len(data["label_conflict_duplicates"]) == 0


def test_controlled_normalization_zero_flips():
    """Verify that lossless PNG re-encoding produced zero prediction flips."""
    norm_path = AUDIT_DIR / "normalized_evaluation.json"
    with open(norm_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["prediction_flips_count"] == 0
    assert data["original_accuracy"] == data["normalized_accuracy"]
    assert data["original_macro_f1"] == data["normalized_macro_f1"]


def test_prediction_csv_test_support():
    """Verify that the test prediction CSV contains exactly 298 items with canonical distribution."""
    assert PREDICTIONS_CSV.exists()
    rows = []
    with open(PREDICTIONS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    assert len(rows) == 298
    class_counts = {}
    for r in rows:
        gt = r["ground_truth_label"]
        class_counts[gt] = class_counts.get(gt, 0) + 1

    assert class_counts == {"fire": 98, "neutral": 100, "smoke": 100}
