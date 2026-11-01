"""
ml/training/config.py - Validated configuration containers for SCOUT training and benchmarking.
"""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union
import torch

from ml.config import (
    CLASS_TO_IDX,
    DEFAULT_BATCH_SIZE,
    DEFAULT_DATASET_ROOT,
    DEFAULT_NUM_WORKERS,
    IMAGE_SIZE,
    PROJECT_ROOT,
    RANDOM_SEED,
)


@dataclass(frozen=True)
class TrainingConfig:
    """
    Validated configuration container for model training.

    Guarantees:
        - num_workers is strictly 0 for deterministic execution and generator restoration.
        - Supported architectures: 'baseline_cnn' or 'mobilenet_v3_small'.
        - Supported initialization modes: 'random' or 'imagenet'.
    """

    # Model architecture and initialization
    model_architecture: str = "baseline_cnn"
    init_mode: str = "random"  # 'random' or 'imagenet'
    local_weights_path: Optional[Path] = None
    weights_id: Optional[str] = "MobileNet_V3_Small_Weights.IMAGENET1K_V1"

    # Dataset & directory paths
    dataset_root: Path = DEFAULT_DATASET_ROOT
    checkpoint_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "checkpoints")
    log_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "logs")

    # Execution hardware & determinism
    device: str = "cpu"
    batch_size: int = DEFAULT_BATCH_SIZE
    num_workers: int = 0  # Strictly 0 for single-process deterministic restoration
    seed: int = RANDOM_SEED

    # Baseline CNN hyperparameters
    baseline_lr: float = 1e-3
    baseline_weight_decay: float = 1e-4
    baseline_max_epochs: int = 25
    baseline_patience: int = 6
    baseline_min_delta: float = 0.001

    # MobileNetV3 Stage 1 hyperparameters (Classifier warmup)
    stage1_epochs: int = 5
    stage1_lr: float = 1e-3
    stage1_weight_decay: float = 1e-4

    # MobileNetV3 Stage 2 hyperparameters (Deep backbone fine-tuning)
    stage2_epochs: int = 20
    stage2_backbone_lr: float = 1e-5
    stage2_classifier_lr: float = 1e-4
    stage2_weight_decay: float = 1e-4
    stage2_patience: int = 6
    stage2_min_delta: float = 0.001

    def __post_init__(self) -> None:
        if self.model_architecture not in ("baseline_cnn", "mobilenet_v3_small"):
            raise ValueError(
                f"Unsupported model_architecture: '{self.model_architecture}'. "
                f"Must be 'baseline_cnn' or 'mobilenet_v3_small'."
            )
        if self.init_mode not in ("random", "imagenet"):
            raise ValueError(
                f"Unsupported init_mode: '{self.init_mode}'. Must be 'random' or 'imagenet'."
            )
        if self.batch_size <= 0:
            raise ValueError(f"batch_size must be positive, got {self.batch_size}")
        if self.num_workers != 0:
            raise ValueError(
                f"num_workers must be 0 for deterministic execution and generator state "
                f"restoration, got {self.num_workers}."
            )
        if self.baseline_lr <= 0 or self.stage1_lr <= 0 or self.stage2_classifier_lr <= 0:
            raise ValueError("All learning rates must be positive.")
        if self.baseline_max_epochs <= 0 or self.stage1_epochs <= 0 or self.stage2_epochs <= 0:
            raise ValueError("Epoch counts must be positive.")

    def to_dict(self) -> Dict[str, Any]:
        """Returns JSON-serializable dictionary representation of config."""
        data = asdict(self)
        data["dataset_root"] = str(self.dataset_root)
        data["checkpoint_dir"] = str(self.checkpoint_dir)
        data["log_dir"] = str(self.log_dir)
        if self.local_weights_path is not None:
            data["local_weights_path"] = str(self.local_weights_path)
        return data


@dataclass(frozen=True)
class BenchmarkConfig:
    """
    Configuration for CPU resource, latency, and memory profiling.
    """

    batch_sizes: Tuple[int, ...] = (32, 16)
    thread_counts: Tuple[int, ...] = (4, 8, 12)
    warmup_batches: int = 2
    measured_batches: int = 10

    # Memory safety thresholds (in bytes)
    min_available_ram_bytes: int = 500 * 1024 * 1024  # 500 MB preflight reserve
    emergency_memory_floor_bytes: int = 400 * 1024 * 1024  # 400 MB emergency abort floor

    def __post_init__(self) -> None:
        if any(b <= 0 for b in self.batch_sizes):
            raise ValueError("All batch sizes must be positive.")
        if any(t <= 0 for t in self.thread_counts):
            raise ValueError("All thread counts must be positive.")
        if self.warmup_batches < 0 or self.measured_batches <= 0:
            raise ValueError("Batch counts must be non-negative and positive respectively.")
        if self.emergency_memory_floor_bytes >= self.min_available_ram_bytes:
            raise ValueError("emergency_memory_floor_bytes must be strictly lower than min_available_ram_bytes.")
