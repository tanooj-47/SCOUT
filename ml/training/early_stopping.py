"""
ml/training/early_stopping.py - Early stopping tracker based on validation macro F1.
"""

import math
from typing import Any, Dict, NamedTuple, Tuple


class EarlyStoppingResult(NamedTuple):
    """
    Structured outcome of an early stopping update step.

    Attributes:
        improved: True if current score improved over best_score by at least min_delta.
        should_stop: True if patience counter reached the patience limit.
    """

    improved: bool
    should_stop: bool


class EarlyStopping:
    """
    Monitors validation macro F1 score with configurable patience and minimum improvement delta.

    Guarantees:
        - Mode is 'max': higher scores represent improvements.
        - Requires score >= best_score + min_delta to register an improvement.
        - Resets patience counter to 0 upon any genuine improvement.
        - Triggers should_stop = True once patience_counter reaches patience limit.
        - Fully serializable state dictionary for checkpointing and resumption.
    """

    def __init__(
        self,
        patience: int = 6,
        min_delta: float = 0.001,
        monitor: str = "val_macro_f1",
    ) -> None:
        if patience <= 0:
            raise ValueError(f"patience must be positive, got {patience}")
        if min_delta < 0:
            raise ValueError(f"min_delta cannot be negative, got {min_delta}")

        self.patience = patience
        self.min_delta = min_delta
        self.monitor = monitor

        self.best_score: float = -float("inf")
        self.patience_counter: int = 0
        self.should_stop: bool = False

    def update(self, current_score: float) -> EarlyStoppingResult:
        """
        Evaluates the current epoch score against the historical best.

        Args:
            current_score: Metric value for the current epoch (e.g., validation macro F1).

        Returns:
            EarlyStoppingResult(improved: bool, should_stop: bool)
            Unpacks directly as a 2-tuple: improved, should_stop = es.update(...)
        """
        if not math.isfinite(current_score):
            raise ValueError(f"current_score must be a finite number, got {current_score}")

        improved = False

        if current_score >= self.best_score + self.min_delta:
            self.best_score = float(current_score)
            self.patience_counter = 0
            self.should_stop = False
            improved = True
        else:
            self.patience_counter += 1
            if self.patience_counter >= self.patience:
                self.should_stop = True

        return EarlyStoppingResult(improved=improved, should_stop=self.should_stop)

    def state_dict(self) -> Dict[str, Any]:
        """Returns internal state dictionary for checkpoint serialization."""
        return {
            "monitor": self.monitor,
            "patience": self.patience,
            "min_delta": self.min_delta,
            "best_score": self.best_score,
            "patience_counter": self.patience_counter,
            "should_stop": self.should_stop,
        }

    def load_state_dict(self, state: Dict[str, Any]) -> None:
        """Restores internal state from a checkpoint dictionary."""
        self.monitor = state.get("monitor", self.monitor)
        self.patience = state.get("patience", self.patience)
        self.min_delta = state.get("min_delta", self.min_delta)
        self.best_score = float(state.get("best_score", -float("inf")))
        self.patience_counter = int(state.get("patience_counter", 0))
        self.should_stop = bool(state.get("should_stop", False))

    def reset(self) -> None:
        """Resets tracker to initial state."""
        self.best_score = -float("inf")
        self.patience_counter = 0
        self.should_stop = False
