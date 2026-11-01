"""
ml/training/checkpoints.py - Atomic checkpoint serialization, trusted loading, and deterministic state restoration.
"""

from datetime import datetime, timezone
import os
from pathlib import Path
import random
import sys
from typing import Any, Dict, Optional, Union
import numpy as np
import sklearn
import torch
import torchvision

from ml.config import (
    CLASS_TO_IDX,
    IDX_TO_CLASS,
    IMAGE_SIZE,
    IMAGENET_MEAN,
    IMAGENET_STD,
    LETTERBOX_FILL_COLOR,
    PROJECT_ROOT,
)


class CheckpointIntegrityError(Exception):
    """Raised when a checkpoint file fails schema or metadata integrity validation."""


class UntrustedCheckpointError(Exception):
    """Raised when an untrusted checkpoint is attempted to be loaded with weights_only=False."""


class CheckpointManager:
    """
    Manages atomic persistence and safe restoration of model, optimizer, scheduler,
    and deterministic pseudorandom number generator states.

    Security & Trust Model:
        - torch.load(..., weights_only=False) utilizes Python's pickle deserializer, which
          carries arbitrary code execution risks.
        - weights_only=False is strictly authorized ONLY for trusted local checkpoints created
          internally within the project's checkpoint directory.
        - External checkpoints must NEVER be loaded through the trusted path; they must use
          weights_only=True.
        - Schema and metadata validation is an internal integrity check, NOT a security boundary.
    """

    def __init__(self, checkpoint_dir: Optional[Union[str, Path]] = None) -> None:
        if checkpoint_dir is None:
            self.checkpoint_dir = PROJECT_ROOT / "checkpoints"
        else:
            self.checkpoint_dir = Path(checkpoint_dir)

        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def capture_rng_states(
        self,
        dataloader_generator: Optional[torch.Generator] = None,
    ) -> Dict[str, Any]:
        """
        Captures Python, NumPy, PyTorch CPU, and DataLoader generator states at the exact
        checkpoint boundary (immediately after completed epoch & validation, before saving).
        """
        return {
            "torch_cpu": torch.get_rng_state(),
            "python": random.getstate(),
            "numpy": np.random.get_state(),
            "dataloader_generator": (
                dataloader_generator.get_state() if dataloader_generator is not None else None
            ),
        }

    def restore_rng_states(
        self,
        rng_states: Dict[str, Any],
        dataloader_generator: Optional[torch.Generator] = None,
    ) -> None:
        """
        Restores Python, NumPy, PyTorch CPU, and DataLoader generator states.
        Must be invoked after all model, optimizer, and loader instantiations are complete
        so initialization does not consume the restored sequence.
        """
        if "torch_cpu" in rng_states and rng_states["torch_cpu"] is not None:
            torch.set_rng_state(rng_states["torch_cpu"])
        if "python" in rng_states and rng_states["python"] is not None:
            random.setstate(rng_states["python"])
        if "numpy" in rng_states and rng_states["numpy"] is not None:
            np.random.set_state(rng_states["numpy"])
        if (
            dataloader_generator is not None
            and "dataloader_generator" in rng_states
            and rng_states["dataloader_generator"] is not None
        ):
            dataloader_generator.set_state(rng_states["dataloader_generator"])

    def save_checkpoint(
        self,
        filename: str,
        model: torch.nn.Module,
        optimizer: torch.optim.Optimizer,
        scheduler: Optional[Any],
        global_epoch: int,
        stage_epoch: int,
        training_stage: Optional[int],
        early_stopping_state: Dict[str, Any],
        current_metrics: Dict[str, Any],
        history: Dict[str, Any],
        config: Dict[str, Any],
        dataloader_generator: Optional[torch.Generator] = None,
        model_architecture: str = "baseline_cnn",
        init_mode: str = "random",
        weights_id: Optional[str] = None,
    ) -> Path:
        """
        Atomically saves a checkpoint using a temporary file in the same directory
        followed by an atomic rename (os.replace).
        """
        target_path = self.checkpoint_dir / filename
        temp_path = self.checkpoint_dir / f"{filename}.tmp.{os.getpid()}"

        # Capture RNG states at this exact serialization boundary
        rng_states = self.capture_rng_states(dataloader_generator=dataloader_generator)

        # Stage-specific optimizer metadata
        optimizer_config = {
            "type": type(optimizer).__name__,
            "learning_rates": [group["lr"] for group in optimizer.param_groups],
            "weight_decay": optimizer.param_groups[0].get("weight_decay", 0.0),
            "param_group_names": [
                group.get("name", f"group_{i}") for i, group in enumerate(optimizer.param_groups)
            ],
        }

        payload: Dict[str, Any] = {
            # Architecture & initialization
            "model_architecture": model_architecture,
            "init_mode": init_mode,
            "weights_id": weights_id,
            "training_stage": training_stage,
            # Core parameter state dicts
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "scheduler_state_dict": scheduler.state_dict() if scheduler else None,
            "optimizer_config": optimizer_config,
            # Progress & tracking
            "global_epoch": global_epoch,
            "stage_epoch": stage_epoch,
            "early_stopping": early_stopping_state,
            "current_metrics": current_metrics,
            "history": history,
            # Invariant metadata
            "class_to_idx": CLASS_TO_IDX,
            "idx_to_class": IDX_TO_CLASS,
            "input_resolution": (IMAGE_SIZE, IMAGE_SIZE),
            "normalization": {
                "mean": IMAGENET_MEAN,
                "std": IMAGENET_STD,
                "letterbox_fill": LETTERBOX_FILL_COLOR,
            },
            # Exact RNG states
            "rng_states": rng_states,
            # Environment telemetry
            "config": config,
            "versions": {
                "python": sys.version,
                "torch": torch.__version__,
                "torchvision": torchvision.__version__,
                "numpy": np.__version__,
                "sklearn": sklearn.__version__,
            },
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }

        try:
            torch.save(payload, temp_path)
            # Atomic filesystem replacement on Windows/NTFS
            os.replace(temp_path, target_path)
            return target_path
        except Exception as exc:
            # Clean up temp file on failure without deleting existing target checkpoint
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise RuntimeError(f"Failed to atomically save checkpoint to '{target_path}': {exc}") from exc

    def load_checkpoint(
        self,
        path: Union[str, Path],
        is_trusted: bool = True,
        weights_only: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Loads and validates a checkpoint file.

        Security Enforcement:
            - If is_trusted is False, weights_only=True is strictly enforced to prevent arbitrary
              code execution via pickle. Requesting weights_only=False on untrusted paths raises
              UntrustedCheckpointError.
            - If is_trusted is True, weights_only defaults to False to permit restoring complete
              optimizer, scheduler, RNG, and dataclass states.

        Integrity Enforcement:
            - Validates that required metadata fields are present and match canonical class mappings.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Checkpoint file does not exist: {file_path}")

        # Enforce security trust boundary
        if not is_trusted:
            if weights_only is False:
                raise UntrustedCheckpointError(
                    f"Refusing to load untrusted checkpoint '{file_path}' with weights_only=False. "
                    f"External checkpoints must be loaded with weights_only=True to prevent code execution."
                )
            weights_only = True
        else:
            if weights_only is None:
                weights_only = False

        try:
            checkpoint = torch.load(file_path, map_location="cpu", weights_only=weights_only)
        except Exception as exc:
            raise CheckpointIntegrityError(f"Failed to load checkpoint at '{file_path}': {exc}") from exc

        # If weights_only was used, checkpoint is a raw state dict; skip full metadata validation
        if weights_only:
            return checkpoint

        # Full Schema Integrity Validation (internal check against state corruption)
        required_keys = [
            "model_architecture",
            "model_state_dict",
            "optimizer_state_dict",
            "class_to_idx",
            "rng_states",
        ]
        missing = [k for k in required_keys if k not in checkpoint]
        if missing:
            raise CheckpointIntegrityError(
                f"Checkpoint '{file_path}' failed integrity validation: missing keys {missing}."
            )

        if checkpoint["class_to_idx"] != CLASS_TO_IDX:
            raise CheckpointIntegrityError(
                f"Checkpoint class mapping {checkpoint['class_to_idx']} does not match canonical "
                f"mapping {CLASS_TO_IDX}."
            )

        return checkpoint
