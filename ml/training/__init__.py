"""
ml/training/__init__.py - Training engine, benchmarking, metrics, and checkpointing package.
"""

from ml.training.benchmark import (
    BenchmarkEmergencyAbortError,
    CPUBenchmark,
    InsufficientMemoryError,
)
from ml.training.checkpoints import (
    CheckpointIntegrityError,
    CheckpointManager,
    UntrustedCheckpointError,
)
from ml.training.config import BenchmarkConfig, TrainingConfig
from ml.training.early_stopping import EarlyStopping, EarlyStoppingResult
from ml.training.engine import (
    GradientDivergenceError,
    InvalidDataError,
    PretrainedWeightsNotFoundError,
    Trainer,
    TrainingDivergenceError,
)
from ml.training.metrics import MetricAccumulator

__all__ = [
    "TrainingConfig",
    "BenchmarkConfig",
    "MetricAccumulator",
    "EarlyStopping",
    "EarlyStoppingResult",
    "CheckpointManager",
    "CheckpointIntegrityError",
    "UntrustedCheckpointError",
    "Trainer",
    "TrainingDivergenceError",
    "GradientDivergenceError",
    "InvalidDataError",
    "PretrainedWeightsNotFoundError",
    "CPUBenchmark",
    "InsufficientMemoryError",
    "BenchmarkEmergencyAbortError",
]
