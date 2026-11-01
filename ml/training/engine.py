"""
ml/training/engine.py - Core training and validation engine with fail-fast validation and stage lifecycle.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import torch
import torch.nn as nn
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import DataLoader

from ml.config import CLASS_TO_IDX, NUM_CLASSES
from ml.data.dataset import get_data_loaders
from ml.models.baseline_cnn import BaselineCNN
from ml.models.mobilenet_v3 import (
    build_mobilenet_v3,
    configure_mobilenet_stage,
    enter_train_mode,
    get_mobilenet_param_groups,
)
from ml.training.checkpoints import CheckpointManager
from ml.training.config import TrainingConfig
from ml.training.early_stopping import EarlyStopping
from ml.training.metrics import MetricAccumulator


class TrainingDivergenceError(Exception):
    """Raised when loss or model logits become non-finite (NaN or Inf)."""


class GradientDivergenceError(Exception):
    """Raised when gradients become non-finite (NaN or Inf) during backpropagation."""


class InvalidDataError(Exception):
    """Raised when input tensors or target class labels fail shape, dtype, or range validation."""


class PretrainedWeightsNotFoundError(Exception):
    """Raised when ImageNet initialization is requested but no verified local weights file is found."""


class Trainer:
    """
    Main training engine for SCOUT wildfire image classification.

    Guarantees:
        - 4-stage step validation: Targets -> Logits -> Loss -> Gradients.
        - Optimizer step is aborted and last valid checkpoint preserved upon any divergence.
        - MobileNetV3 enforces enter_train_mode(model, stage) and freeze_batchnorm_running_stats every epoch.
        - Stage 1 -> Stage 2 transition creates a fresh optimizer and scheduler, discarding Stage 1 optimizer state.
        - Captures RNG states at the exact post-epoch/post-validation boundary before checkpoint serialization.
    """

    def __init__(
        self,
        config: TrainingConfig,
        checkpoint_manager: Optional[CheckpointManager] = None,
    ) -> None:
        self.config = config
        self.checkpoint_manager = checkpoint_manager or CheckpointManager(config.checkpoint_dir)
        self.criterion = nn.CrossEntropyLoss()
        self.device = torch.device(config.device)

        # Dedicated DataLoader generator for deterministic shuffle sequencing
        self.train_generator = torch.Generator().manual_seed(config.seed)

        # Build model based on architecture and initialization mode
        self.model = self._build_model()
        self.model.to(self.device)

        # Optimizer, scheduler, and early-stopping placeholders
        self.optimizer: Optional[torch.optim.Optimizer] = None
        self.scheduler: Optional[Any] = None
        self.early_stopping: Optional[EarlyStopping] = None

        # Tracking state
        self.global_epoch: int = 0
        self.stage_epoch: int = 0
        self.current_stage: Optional[int] = None
        self.history: Dict[str, Any] = {"train_loss": [], "val_metrics": []}

        # Initialize optimization components for target architecture
        self._setup_initial_optimization()

    def _build_model(self) -> nn.Module:
        """Instantiates model architecture according to configuration."""
        if self.config.model_architecture == "baseline_cnn":
            return BaselineCNN(num_classes=NUM_CLASSES)

        elif self.config.model_architecture == "mobilenet_v3_small":
            if self.config.init_mode == "random":
                # Offline by construction; lightweight architecture trained from scratch
                return build_mobilenet_v3(num_classes=NUM_CLASSES, pretrained=False)

            elif self.config.init_mode == "imagenet":
                # Explicit opt-in only; requires verified local weights
                weights_path = self.config.local_weights_path
                if weights_path is None or not Path(weights_path).exists():
                    raise PretrainedWeightsNotFoundError(
                        f"ImageNet initialization requested (init_mode='imagenet'), but local "
                        f"weights file was not found at '{weights_path}'. Automated network downloading "
                        f"is disabled. Please provide the verified weights file or select init_mode='random'."
                    )
                # Load verified local weights safely with weights_only=True
                model = build_mobilenet_v3(num_classes=NUM_CLASSES, pretrained=False)
                state_dict = torch.load(weights_path, map_location="cpu", weights_only=True)
                model.load_state_dict(state_dict)
                return model

            else:
                raise ValueError(f"Unknown init_mode: {self.config.init_mode}")

        else:
            raise ValueError(f"Unknown model_architecture: {self.config.model_architecture}")

    def _setup_initial_optimization(self) -> None:
        """Sets up initial optimizer, scheduler, and early stopping."""
        if self.config.model_architecture == "baseline_cnn":
            self.current_stage = None
            self.optimizer = torch.optim.AdamW(
                self.model.parameters(),
                lr=self.config.baseline_lr,
                weight_decay=self.config.baseline_weight_decay,
            )
            self.scheduler = CosineAnnealingLR(
                self.optimizer,
                T_max=self.config.baseline_max_epochs,
                eta_min=1e-5,
            )
            self.early_stopping = EarlyStopping(
                patience=self.config.baseline_patience,
                min_delta=self.config.baseline_min_delta,
            )

        elif self.config.model_architecture == "mobilenet_v3_small":
            # Initialize for Stage 1 (Classifier warmup)
            self.current_stage = 1
            configure_mobilenet_stage(self.model, stage=1)
            param_groups = get_mobilenet_param_groups(
                self.model,
                stage=1,
                stage1_lr=self.config.stage1_lr,
                weight_decay=self.config.stage1_weight_decay,
            )
            self.optimizer = torch.optim.AdamW(param_groups)
            self.scheduler = CosineAnnealingLR(
                self.optimizer,
                T_max=self.config.stage1_epochs,
                eta_min=1e-5,
            )
            # Early stopping not typically applied in short 5-epoch Stage 1 warmup
            self.early_stopping = None

    def validate_inputs(self, images: torch.Tensor, targets: torch.Tensor) -> None:
        """
        Stage 1 Validation: Validates target tensor shape, dtype, and class range.
        Executed before model forward pass and loss computation.
        """
        if targets.ndim != 1 or targets.shape[0] != images.shape[0]:
            raise InvalidDataError(
                f"Invalid target tensor shape: {targets.shape}, expected ({images.shape[0]},)."
            )
        if targets.dtype not in (torch.int64, torch.long):
            raise InvalidDataError(f"Target tensor dtype must be torch.long, got {targets.dtype}.")
        if (targets < 0).any() or (targets >= NUM_CLASSES).any():
            raise InvalidDataError(
                f"Target labels contain values out of valid range [0, {NUM_CLASSES - 1}]. "
                f"Min label: {targets.min().item()}, Max label: {targets.max().item()}."
            )

    def validate_logits(self, images: torch.Tensor, logits: torch.Tensor) -> None:
        """
        Stage 2 Validation: Validates logit shape and finiteness after forward pass.
        """
        if logits.shape != (images.shape[0], NUM_CLASSES):
            raise TrainingDivergenceError(
                f"Logit shape mismatch: {logits.shape}, expected ({images.shape[0]}, {NUM_CLASSES})."
            )
        if not torch.isfinite(logits).all():
            raise TrainingDivergenceError("Model forward pass produced non-finite logits (NaN or Inf).")

    def validate_loss(self, loss: torch.Tensor) -> None:
        """
        Stage 3 Validation: Validates scalar dimension and finiteness of computed loss.
        """
        if loss.ndim != 0:
            raise TrainingDivergenceError(f"Loss must be scalar, got shape {loss.shape}.")
        if not torch.isfinite(loss):
            raise TrainingDivergenceError(
                f"Loss computed as non-finite value ({loss.item()}). Halting optimization."
            )

    def validate_gradients(self) -> None:
        """
        Stage 4 Validation: Verifies all trainable parameter gradients are finite before optimizer.step().
        """
        for name, param in self.model.named_parameters():
            if param.requires_grad and param.grad is not None:
                if not torch.isfinite(param.grad).all():
                    # Abort: zero gradients to protect model parameters from corruption
                    if self.optimizer is not None:
                        self.optimizer.zero_grad(set_to_none=True)
                    raise GradientDivergenceError(
                        f"Non-finite gradient (NaN or Inf) detected in parameter '{name}'. "
                        f"Aborting optimizer step."
                    )

    def train_step(
        self,
        images: torch.Tensor,
        targets: torch.Tensor,
    ) -> float:
        """
        Executes a single training forward, loss, backward, and optimization step with fail-fast guards.
        """
        images = images.to(self.device)
        targets = targets.to(self.device)

        if self.optimizer is None:
            raise RuntimeError("Optimizer is not initialized.")

        # Stage 1: Validate inputs before forward pass and loss computation
        self.validate_inputs(images, targets)

        self.optimizer.zero_grad()

        # Forward pass
        logits = self.model(images)

        # Stage 2: Validate logits
        self.validate_logits(images, logits)

        # Loss computation
        loss = self.criterion(logits, targets)

        # Stage 3: Validate loss
        self.validate_loss(loss)

        # Backward pass
        loss.backward()

        # Stage 4: Validate gradients
        self.validate_gradients()

        # Optimizer step
        self.optimizer.step()

        return float(loss.item())

    def train_epoch(self, train_loader: DataLoader) -> float:
        """
        Executes one full training epoch over the training DataLoader.
        """
        if self.config.model_architecture == "mobilenet_v3_small":
            # Strictly enforce BatchNorm evaluation policy and training mode
            stage = self.current_stage or 1
            enter_train_mode(self.model, stage=stage)
        else:
            self.model.train()

        total_loss = 0.0
        batch_count = 0

        for images, targets in train_loader:
            loss_val = self.train_step(images, targets)
            total_loss += loss_val
            batch_count += 1

        if batch_count == 0:
            raise RuntimeError("train_loader contained zero batches.")

        return total_loss / batch_count

    def validate(self, val_loader: DataLoader) -> Dict[str, Any]:
        """
        Executes validation epoch over the complete validation split using MetricAccumulator.
        """
        self.model.eval()
        accumulator = MetricAccumulator()
        total_loss = 0.0
        batch_count = 0

        with torch.no_grad():
            for images, targets in val_loader:
                images = images.to(self.device)
                targets = targets.to(self.device)

                logits = self.model(images)
                if not torch.isfinite(logits).all():
                    raise TrainingDivergenceError("Non-finite logits detected during validation pass.")

                loss = self.criterion(logits, targets)
                total_loss += float(loss.item())
                batch_count += 1

                accumulator.update(targets, logits)

        metrics = accumulator.compute()
        mean_loss = total_loss / max(batch_count, 1)
        metrics["val_loss"] = round(mean_loss, 4)
        metrics["loss"] = round(mean_loss, 4)
        return metrics

    def step_scheduler(self) -> Optional[float]:
        """
        Steps the learning rate scheduler at the end of an epoch.
        Returns the updated learning rate, or None if no scheduler is active.
        """
        if self.scheduler is not None:
            self.scheduler.step()
            return float(self.scheduler.get_last_lr()[0])
        return None

    def transition_to_stage2(
        self,
        stage1_checkpoint_path: Optional[Union[str, Path]] = None,
    ) -> None:
        """
        Transitions MobileNetV3 from Stage 1 to Stage 2:
        1. Selects and loads the best Stage 1 model weights.
        2. Configures Stage 2 parameter freezing (unfreezes features[9:] and classifier).
        3. Creates a fresh Stage 2 optimizer (Stage 1 optimizer state is discarded).
        4. Creates a fresh Stage 2 scheduler.
        5. Resets stage-local epoch counter and early stopping.
        6. Preserves overall experiment history.
        7. Records transition metadata in experiment logs.
        """
        if self.config.model_architecture != "mobilenet_v3_small":
            raise ValueError("Stage transitions are only applicable to MobileNetV3.")

        # 1. Select and load the best Stage 1 model weights
        if stage1_checkpoint_path is None:
            default_best = self.checkpoint_manager.checkpoint_dir / "mobilenet_v3_small_stage1_best.pt"
            if default_best.exists():
                stage1_checkpoint_path = default_best

        if stage1_checkpoint_path is not None:
            ckpt = self.checkpoint_manager.load_checkpoint(stage1_checkpoint_path, is_trusted=True)
            self.model.load_state_dict(ckpt["model_state_dict"])

        # 2. Unfreeze features[9:] and classifier
        self.current_stage = 2
        configure_mobilenet_stage(self.model, stage=2)

        # 3. Fresh optimizer with differential learning rates (Stage 1 optimizer state discarded)
        param_groups = get_mobilenet_param_groups(
            self.model,
            stage=2,
            backbone_lr=self.config.stage2_backbone_lr,
            classifier_lr=self.config.stage2_classifier_lr,
            weight_decay=self.config.stage2_weight_decay,
        )
        self.optimizer = torch.optim.AdamW(param_groups)

        # 4. Fresh Stage 2 scheduler
        self.scheduler = CosineAnnealingLR(
            self.optimizer,
            T_max=self.config.stage2_epochs,
            eta_min=1e-6,
        )

        # 5. Reset stage-local epoch counter and early stopping
        self.stage_epoch = 0
        self.early_stopping = EarlyStopping(
            patience=self.config.stage2_patience,
            min_delta=self.config.stage2_min_delta,
        )

        # 6. Archive stage 1 logs
        if "stage_1" not in self.history:
            self.history["stage_1"] = {
                "train_loss": list(self.history.get("train_loss", [])),
                "val_metrics": list(self.history.get("val_metrics", [])),
            }
            self.history["train_loss"] = []
            self.history["val_metrics"] = []

    def step_early_stopping(self, current_score: float) -> Tuple[bool, bool]:
        """
        Updates the internal early stopping tracker with the current validation score.

        Args:
            current_score: Metric value for the current epoch (e.g., validation macro F1).

        Returns:
            Tuple of (improved: bool, should_stop: bool). Returns (False, False) if early stopping is disabled.
        """
        if self.early_stopping is None:
            return False, False
        return self.early_stopping.update(current_score)

    def save_epoch_checkpoint(
        self,
        val_metrics: Dict[str, Any],
        is_best: bool = False,
    ) -> Tuple[Path, Optional[Path]]:
        """
        Atomically saves the current training epoch checkpoint and optionally the best checkpoint.
        """
        if not isinstance(is_best, bool):
            raise TypeError(
                f"is_best must be a strict boolean (True or False), got {type(is_best).__name__}: {is_best!r}. "
                "Ensure EarlyStopping.update() return values are unpacked into (improved, should_stop) "
                "before passing is_best."
            )
        model_name = self.config.model_architecture
        stage_suffix = f"_stage{self.current_stage}" if self.current_stage else ""

        early_stopping_state = self.early_stopping.state_dict() if self.early_stopping else {}

        last_filename = f"{model_name}{stage_suffix}_last.pt"
        last_path = self.checkpoint_manager.save_checkpoint(
            filename=last_filename,
            model=self.model,
            optimizer=self.optimizer,
            scheduler=self.scheduler,
            global_epoch=self.global_epoch,
            stage_epoch=self.stage_epoch,
            training_stage=self.current_stage,
            early_stopping_state=early_stopping_state,
            current_metrics=val_metrics,
            history=self.history,
            config=self.config.to_dict(),
            dataloader_generator=self.train_generator,
            model_architecture=self.config.model_architecture,
            init_mode=self.config.init_mode,
            weights_id=self.config.weights_id,
        )

        best_path: Optional[Path] = None
        if is_best:
            best_filename = f"{model_name}{stage_suffix}_best.pt"
            best_path = self.checkpoint_manager.save_checkpoint(
                filename=best_filename,
                model=self.model,
                optimizer=self.optimizer,
                scheduler=self.scheduler,
                global_epoch=self.global_epoch,
                stage_epoch=self.stage_epoch,
                training_stage=self.current_stage,
                early_stopping_state=early_stopping_state,
                current_metrics=val_metrics,
                history=self.history,
                config=self.config.to_dict(),
                dataloader_generator=self.train_generator,
                model_architecture=self.config.model_architecture,
                init_mode=self.config.init_mode,
                weights_id=self.config.weights_id,
            )

        return last_path, best_path

    def resume_from_checkpoint(self, checkpoint_path: Union[str, Path]) -> None:
        """
        Resumes training from a saved trusted checkpoint.

        Restoration Order:
            1. Load and validate schema.
            2. Reconfigure model architecture & stage.
            3. Load model parameters.
            4. Reconstruct and load optimizer & scheduler.
            5. Restore early stopping state.
            6. Restore RNG states and DataLoader generator state AFTER all initializations.
        """
        checkpoint = self.checkpoint_manager.load_checkpoint(checkpoint_path, is_trusted=True)

        # 1. Validate architecture match
        if checkpoint["model_architecture"] != self.config.model_architecture:
            raise ValueError(
                f"Checkpoint architecture '{checkpoint['model_architecture']}' does not match "
                f"current config '{self.config.model_architecture}'."
            )

        # 2. Stage configuration
        self.current_stage = checkpoint.get("training_stage")
        if self.config.model_architecture == "mobilenet_v3_small" and self.current_stage:
            configure_mobilenet_stage(self.model, stage=self.current_stage)

        # 3. Load model parameters
        self.model.load_state_dict(checkpoint["model_state_dict"])

        # 4. Reconstruct optimizer and scheduler
        if self.config.model_architecture == "mobilenet_v3_small" and self.current_stage == 2:
            param_groups = get_mobilenet_param_groups(
                self.model,
                stage=2,
                backbone_lr=self.config.stage2_backbone_lr,
                classifier_lr=self.config.stage2_classifier_lr,
                weight_decay=self.config.stage2_weight_decay,
            )
            self.optimizer = torch.optim.AdamW(param_groups)
            self.scheduler = CosineAnnealingLR(
                self.optimizer,
                T_max=self.config.stage2_epochs,
                eta_min=1e-6,
            )
        elif self.config.model_architecture == "mobilenet_v3_small" and self.current_stage == 1:
            param_groups = get_mobilenet_param_groups(
                self.model,
                stage=1,
                stage1_lr=self.config.stage1_lr,
                weight_decay=self.config.stage1_weight_decay,
            )
            self.optimizer = torch.optim.AdamW(param_groups)
            self.scheduler = CosineAnnealingLR(
                self.optimizer,
                T_max=self.config.stage1_epochs,
                eta_min=1e-5,
            )
        else:
            self.optimizer = torch.optim.AdamW(
                self.model.parameters(),
                lr=self.config.baseline_lr,
                weight_decay=self.config.baseline_weight_decay,
            )
            self.scheduler = CosineAnnealingLR(
                self.optimizer,
                T_max=self.config.baseline_max_epochs,
                eta_min=1e-5,
            )

        self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        if self.scheduler and checkpoint.get("scheduler_state_dict"):
            self.scheduler.load_state_dict(checkpoint["scheduler_state_dict"])

        # 5. Restore progress counters & history
        self.global_epoch = checkpoint.get("global_epoch", 0)
        self.stage_epoch = checkpoint.get("stage_epoch", 0)
        self.history = checkpoint.get("history", {"train_loss": [], "val_metrics": []})

        # 6. Restore early stopping
        if self.early_stopping and checkpoint.get("early_stopping"):
            self.early_stopping.load_state_dict(checkpoint["early_stopping"])

        # 7. Restore RNG and DataLoader generator states LAST so construction doesn't consume them
        self.checkpoint_manager.restore_rng_states(
            checkpoint["rng_states"],
            dataloader_generator=self.train_generator,
        )
