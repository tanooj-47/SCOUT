"""
ml/training/metrics.py - Whole-split metric accumulator and classification evaluation.
"""

from typing import Any, Dict, List, Optional, Union
import numpy as np
from sklearn.metrics import classification_report, confusion_matrix
import torch

from ml.config import CLASS_NAMES, CLASS_TO_IDX, NUM_CLASSES


class MetricAccumulator:
    """
    Accumulates predictions and ground truth labels across all validation batches
    to calculate unbiased global metrics over the complete partition.

    Guarantees:
        - Rejects batch-averaging distortion: metrics are calculated globally.
        - Enforces explicit class labels [0, 1, 2] corresponding to ('fire', 'neutral', 'smoke').
        - Uses zero_division=0: classes with zero predictions yield 0.0 without NaNs or warnings.
        - Macro F1 is computed as the strict mean of all 3 class F1 scores.
    """

    def __init__(self) -> None:
        self.y_true_list: List[int] = []
        self.y_pred_list: List[int] = []

    def update(
        self,
        y_true: Union[torch.Tensor, np.ndarray, List[int]],
        y_pred: Union[torch.Tensor, np.ndarray, List[int]],
    ) -> None:
        """
        Accumulates ground truths and predictions from a batch.

        Args:
            y_true: Target labels of shape (batch_size,)
            y_pred: Predicted class labels of shape (batch_size,) OR raw logits of shape (batch_size, num_classes)
        """
        # Convert y_true to list of integers
        if isinstance(y_true, torch.Tensor):
            y_true_clean = y_true.detach().cpu().long().numpy().tolist()
        elif isinstance(y_true, np.ndarray):
            y_true_clean = y_true.astype(int).tolist()
        else:
            y_true_clean = [int(v) for v in y_true]

        # Convert y_pred to list of integer class predictions
        if isinstance(y_pred, torch.Tensor):
            y_pred_detach = y_pred.detach().cpu()
            if y_pred_detach.ndim == 2:
                # Raw logits: take argmax along class dimension
                y_pred_clean = torch.argmax(y_pred_detach, dim=-1).long().numpy().tolist()
            else:
                y_pred_clean = y_pred_detach.long().numpy().tolist()
        elif isinstance(y_pred, np.ndarray):
            if y_pred.ndim == 2:
                y_pred_clean = np.argmax(y_pred, axis=-1).astype(int).tolist()
            else:
                y_pred_clean = y_pred.astype(int).tolist()
        else:
            y_pred_clean = [int(v) for v in y_pred]

        if len(y_true_clean) != len(y_pred_clean):
            raise ValueError(
                f"Batch dimension mismatch: y_true has {len(y_true_clean)} samples, "
                f"y_pred has {len(y_pred_clean)} samples."
            )

        self.y_true_list.extend(y_true_clean)
        self.y_pred_list.extend(y_pred_clean)

    def compute(self) -> Dict[str, Any]:
        """
        Computes comprehensive evaluation metrics over all accumulated samples.

        Returns:
            Dictionary containing:
                - accuracy: float
                - macro_f1: float
                - per_class: Dict[str, Dict[str, float]]
                - confusion_matrix: List[List[int]] (3x3)
                - total_samples: int
        """
        if not self.y_true_list:
            raise RuntimeError("No samples accumulated. Call update() before compute().")

        y_true_arr = np.array(self.y_true_list, dtype=int)
        y_pred_arr = np.array(self.y_pred_list, dtype=int)

        labels = [0, 1, 2]
        target_names = list(CLASS_NAMES)  # ['fire', 'neutral', 'smoke']

        # 3x3 Confusion Matrix
        conf_mat = confusion_matrix(
            y_true_arr,
            y_pred_arr,
            labels=labels,
        )

        # Scikit-learn classification report with zero_division=0
        report = classification_report(
            y_true_arr,
            y_pred_arr,
            labels=labels,
            target_names=target_names,
            output_dict=True,
            zero_division=0,
        )

        per_class: Dict[str, Dict[str, float]] = {}
        for name in target_names:
            c_metrics = report[name]
            per_class[name] = {
                "precision": float(c_metrics["precision"]),
                "recall": float(c_metrics["recall"]),
                "f1": float(c_metrics["f1-score"]),
                "support": int(c_metrics["support"]),
            }

        # Strict macro and weighted metrics calculated over all 3 classes
        macro_f1 = float(report["macro avg"]["f1-score"])
        macro_precision = float(report["macro avg"]["precision"])
        macro_recall = float(report["macro avg"]["recall"])
        weighted_f1 = float(report["weighted avg"]["f1-score"])
        accuracy = float(report["accuracy"])

        return {
            "accuracy": accuracy,
            "macro_f1": macro_f1,
            "macro_precision": macro_precision,
            "macro_recall": macro_recall,
            "weighted_f1": weighted_f1,
            "per_class": per_class,
            "confusion_matrix": conf_mat.tolist(),
            "total_samples": len(self.y_true_list),
        }

    def reset(self) -> None:
        """Clears accumulated samples."""
        self.y_true_list.clear()
        self.y_pred_list.clear()
