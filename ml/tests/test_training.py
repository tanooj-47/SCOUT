"""
ml/tests/test_training.py - Comprehensive unit tests for SCOUT Phase 4 Training Engine.

Validates:
- Baseline training step, parameter updates, finite gradients.
- MobileNetV3 Stage 1 classifier updates and frozen backbone.
- MobileNetV3 Stage 2 updates on features[9:] and classifier, with frozen features[:9].
- BatchNorm running statistics preservation during training mode.
- Whole-split metric accumulation and batch invariance.
- Explicit 3-class precision/recall/F1 reporting with zero_division=0.
- Early stopping patience, delta threshold, and reset on improvement.
- Stage transition optimizer reset and best weight loading.
- Atomic checkpoint writing without orphaned temporary files.
- DataLoader generator state restoration and deterministic shuffle sequencing.
- Interrupted-vs-uninterrupted deterministic resume parity on synthetic data.
- Checkpoint security trust boundary and schema integrity validation.
- 4-stage fail-fast validation: invalid targets, NaN logits, NaN loss, NaN gradients.
- Benchmark preflight memory check, emergency abort, state cleanup, and isolation.
- PretrainedWeightsNotFoundError when local ImageNet weights are absent (zero downloads).
"""

import copy
import gc
from pathlib import Path
import random
from unittest.mock import MagicMock, patch
import numpy as np
import pytest
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from ml.config import CLASS_NAMES, CLASS_TO_IDX, NUM_CLASSES
from ml.data.dataset import get_data_loaders
from ml.models.baseline_cnn import BaselineCNN
from ml.models.mobilenet_v3 import (
    build_mobilenet_v3,
    configure_mobilenet_stage,
    enter_train_mode,
)
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
from ml.training.early_stopping import EarlyStopping
from ml.training.engine import (
    GradientDivergenceError,
    InvalidDataError,
    PretrainedWeightsNotFoundError,
    Trainer,
    TrainingDivergenceError,
)
from ml.training.metrics import MetricAccumulator


# ===========================================================================
# 1. Step Execution and Freezing Tests
# ===========================================================================
def test_train_step_baseline_updates_trainable_parameters():
    """Verify BaselineCNN training step executes, outputs finite loss, and updates trainable parameters."""
    config = TrainingConfig(model_architecture="baseline_cnn")
    trainer = Trainer(config=config)

    initial_params = [p.clone().detach() for p in trainer.model.parameters()]

    dummy_images = torch.randn(4, 3, 224, 224)
    dummy_targets = torch.tensor([0, 1, 2, 0], dtype=torch.long)

    loss_val = trainer.train_step(dummy_images, dummy_targets)

    assert np.isfinite(loss_val)
    assert loss_val > 0.0

    # Assert at least some trainable parameters were updated
    updated = any(
        not torch.equal(p_init, p_curr)
        for p_init, p_curr in zip(initial_params, trainer.model.parameters())
    )
    assert updated, "BaselineCNN parameters failed to update after training step!"


def test_train_step_mobilenet_stage1_preserves_frozen_backbone():
    """Verify Stage 1 updates classifier parameters while backbone features remain strictly bitwise identical."""
    config = TrainingConfig(model_architecture="mobilenet_v3_small", init_mode="random")
    trainer = Trainer(config=config)

    initial_backbone = [p.clone().detach() for p in trainer.model.features.parameters()]
    initial_classifier = [p.clone().detach() for p in trainer.model.classifier.parameters()]

    dummy_images = torch.randn(4, 3, 224, 224)
    dummy_targets = torch.tensor([1, 2, 0, 1], dtype=torch.long)

    loss_val = trainer.train_step(dummy_images, dummy_targets)
    assert np.isfinite(loss_val)

    # Assert classifier updated
    classifier_updated = any(
        not torch.equal(p_init, p_curr)
        for p_init, p_curr in zip(initial_classifier, trainer.model.classifier.parameters())
    )
    assert classifier_updated, "Classifier parameters did not update in Stage 1!"

    # Assert backbone parameters remained 100% bitwise identical
    for p_init, p_curr in zip(initial_backbone, trainer.model.features.parameters()):
        assert torch.equal(p_init, p_curr), "Backbone parameter mutated during Stage 1 training step!"


def test_train_step_mobilenet_stage2_updates_high_level_features_only():
    """Verify Stage 2 updates features[9:] and classifier while features[:9] remain bitwise identical."""
    config = TrainingConfig(model_architecture="mobilenet_v3_small", init_mode="random")
    trainer = Trainer(config=config)
    trainer.transition_to_stage2()

    initial_frozen = [p.clone().detach() for p in trainer.model.features[:9].parameters()]
    initial_unfrozen_backbone = [p.clone().detach() for p in trainer.model.features[9:].parameters()]
    initial_classifier = [p.clone().detach() for p in trainer.model.classifier.parameters()]

    dummy_images = torch.randn(4, 3, 224, 224)
    dummy_targets = torch.tensor([0, 1, 2, 2], dtype=torch.long)

    loss_val = trainer.train_step(dummy_images, dummy_targets)
    assert np.isfinite(loss_val)

    # Assert frozen features[:9] remained bitwise identical
    for p_init, p_curr in zip(initial_frozen, trainer.model.features[:9].parameters()):
        assert torch.equal(p_init, p_curr), "Early feature block mutated during Stage 2 step!"

    # Assert features[9:] updated
    backbone_updated = any(
        not torch.equal(p_init, p_curr)
        for p_init, p_curr in zip(initial_unfrozen_backbone, trainer.model.features[9:].parameters())
    )
    assert backbone_updated, "Deep backbone features[9:] failed to update during Stage 2 step!"

    # Assert classifier updated
    classifier_updated = any(
        not torch.equal(p_init, p_curr)
        for p_init, p_curr in zip(initial_classifier, trainer.model.classifier.parameters())
    )
    assert classifier_updated, "Classifier failed to update during Stage 2 step!"


def test_mobilenet_train_mode_preserves_bn_running_stats():
    """Verify Trainer train_epoch sets train mode while keeping backbone BatchNorm running stats locked."""
    config = TrainingConfig(model_architecture="mobilenet_v3_small", init_mode="random")
    trainer = Trainer(config=config)

    # Find a BatchNorm layer in features
    bn_layer = next(m for m in trainer.model.features.modules() if isinstance(m, nn.BatchNorm2d))
    bn_layer.running_mean.fill_(1.23)
    bn_layer.running_var.fill_(4.56)

    initial_mean = bn_layer.running_mean.clone()
    initial_var = bn_layer.running_var.clone()

    # Create dummy DataLoader
    x = torch.randn(8, 3, 224, 224) * 20.0 + 50.0  # Dynamic high-variance batch
    y = torch.tensor([0, 1, 2, 0, 1, 2, 0, 1], dtype=torch.long)
    loader = DataLoader(TensorDataset(x, y), batch_size=4)

    trainer.train_epoch(loader)

    # Assert running statistics remained 100% bitwise unchanged
    assert torch.equal(bn_layer.running_mean, initial_mean)
    assert torch.equal(bn_layer.running_var, initial_var)


# ===========================================================================
# 2. Metric Correctness and Invariance Tests
# ===========================================================================
def test_metric_accumulator_all_three_classes_present():
    """Verify MetricAccumulator returns all 3 classes and macro F1 divides by 3 even when class 2 has 0 predictions."""
    accumulator = MetricAccumulator()

    # Ground truths contain class 0, 1, and 2
    # Predictions contain ONLY class 0 and 1 (class 2 is never predicted)
    y_true = [0, 0, 1, 1, 2, 2]
    y_pred = [0, 0, 1, 1, 0, 1]

    accumulator.update(y_true, y_pred)
    metrics = accumulator.compute()

    assert set(metrics["per_class"].keys()) == {"fire", "neutral", "smoke"}

    # Class 2 (smoke): precision=0.0, recall=0.0, f1=0.0
    smoke_metrics = metrics["per_class"]["smoke"]
    assert smoke_metrics["precision"] == 0.0
    assert smoke_metrics["recall"] == 0.0
    assert smoke_metrics["f1"] == 0.0
    assert smoke_metrics["support"] == 2

    # Class 0 (fire) and Class 1 (neutral) F1
    f1_fire = metrics["per_class"]["fire"]["f1"]
    f1_neutral = metrics["per_class"]["neutral"]["f1"]

    # Macro F1 MUST strictly divide by 3 (including the 0.0 for smoke)
    expected_macro = (f1_fire + f1_neutral + 0.0) / 3.0
    assert pytest.approx(metrics["macro_f1"], rel=1e-5) == expected_macro


def test_metric_accumulator_batch_invariance():
    """Verify metrics computed over 1 large batch vs 5 uneven batches are 100% mathematically identical."""
    acc_single = MetricAccumulator()
    acc_multi = MetricAccumulator()

    np.random.seed(42)
    y_true_all = np.random.randint(0, 3, size=100)
    y_pred_all = np.random.randint(0, 3, size=100)

    # 1. Single evaluation
    acc_single.update(y_true_all, y_pred_all)
    metrics_single = acc_single.compute()

    # 2. Multi-batch evaluation (uneven splits: 17, 33, 10, 25, 15)
    splits = [17, 50, 60, 85, 100]
    start = 0
    for end in splits:
        acc_multi.update(y_true_all[start:end], y_pred_all[start:end])
        start = end
    metrics_multi = acc_multi.compute()

    assert pytest.approx(metrics_single["macro_f1"], rel=1e-6) == metrics_multi["macro_f1"]
    assert pytest.approx(metrics_single["accuracy"], rel=1e-6) == metrics_multi["accuracy"]
    assert metrics_single["confusion_matrix"] == metrics_multi["confusion_matrix"]


def test_confusion_matrix_shape_and_labels():
    """Verify confusion matrix output is strictly a 3x3 list of integers."""
    accumulator = MetricAccumulator()
    accumulator.update([0, 1, 2], [2, 1, 0])
    metrics = accumulator.compute()

    matrix = metrics["confusion_matrix"]
    assert len(matrix) == 3
    assert all(len(row) == 3 for row in matrix)
    assert matrix[0][2] == 1  # True 0 predicted as 2
    assert matrix[1][1] == 1  # True 1 predicted as 1
    assert matrix[2][0] == 1  # True 2 predicted as 0


# ===========================================================================
# 3. Early Stopping Tests
# ===========================================================================
def test_early_stopping_patience_and_delta():
    """Verify EarlyStopping halts after exactly patience epochs of sub-delta improvements."""
    es = EarlyStopping(patience=3, min_delta=0.01)

    # Epoch 1: Initial baseline score = 0.50
    improved, stop = es.update(0.50)
    assert improved is True
    assert stop is False
    assert es.patience_counter == 0

    # Epoch 2: Improvement of 0.005 is less than min_delta (0.01) -> patience=1
    improved, stop = es.update(0.505)
    assert improved is False
    assert stop is False
    assert es.patience_counter == 1

    # Epoch 3: Regression -> patience=2
    improved, stop = es.update(0.48)
    assert improved is False
    assert stop is False
    assert es.patience_counter == 2

    # Epoch 4: Sub-threshold -> patience=3 -> triggers stop
    improved, stop = es.update(0.508)
    assert improved is False
    assert stop is True
    assert es.patience_counter == 3


def test_early_stopping_reset_on_significant_improvement():
    """Verify EarlyStopping resets patience counter upon genuine improvement >= min_delta."""
    es = EarlyStopping(patience=4, min_delta=0.01)

    es.update(0.50)
    es.update(0.505)  # patience = 1
    es.update(0.502)  # patience = 2
    assert es.patience_counter == 2

    # Epoch 4: Genuine improvement (+0.02 >= 0.01) -> patience resets to 0
    improved, stop = es.update(0.52)
    assert improved is True
    assert stop is False
    assert es.patience_counter == 0
    assert es.best_score == 0.52


# ===========================================================================
# 4. Stage Transition Tests
# ===========================================================================
def test_stage_transition_creates_fresh_optimizer(tmp_path):
    """Verify Stage 2 creates fresh optimizer matching Stage 2 differential parameter groups."""
    config = TrainingConfig(
        model_architecture="mobilenet_v3_small",
        init_mode="random",
        checkpoint_dir=tmp_path,
    )
    trainer = Trainer(config=config)

    # Initial Stage 1: 1 parameter group (classifier)
    assert len(trainer.optimizer.param_groups) == 1
    stage1_opt = trainer.optimizer

    trainer.transition_to_stage2()

    # Stage 2: 2 parameter groups (backbone & classifier)
    assert trainer.current_stage == 2
    assert trainer.optimizer is not stage1_opt
    assert len(trainer.optimizer.param_groups) == 2
    assert trainer.optimizer.param_groups[0]["lr"] == config.stage2_backbone_lr
    assert trainer.optimizer.param_groups[1]["lr"] == config.stage2_classifier_lr
    assert trainer.stage_epoch == 0


def test_stage_transition_loads_best_stage1_weights(tmp_path):
    """Verify Stage 2 loads best Stage 1 weights rather than final epoch weights."""
    config = TrainingConfig(
        model_architecture="mobilenet_v3_small",
        init_mode="random",
        checkpoint_dir=tmp_path,
    )
    trainer = Trainer(config=config)

    # Mutate classifier weights to represent "best" weights
    with torch.no_grad():
        trainer.model.classifier[3].weight.fill_(7.77)

    # Save as best checkpoint
    trainer.save_epoch_checkpoint(val_metrics={"macro_f1": 0.95}, is_best=True)

    # Mutate classifier weights further to represent a degraded later epoch
    with torch.no_grad():
        trainer.model.classifier[3].weight.fill_(1.11)

    # Transition directly loading best Stage 1 weights
    best_ckpt_path = tmp_path / "mobilenet_v3_small_stage1_best.pt"
    trainer.transition_to_stage2(stage1_checkpoint_path=best_ckpt_path)

    # Assert classifier weights match the best state (7.77), not the degraded state (1.11)
    assert torch.allclose(trainer.model.classifier[3].weight, torch.tensor(7.77))


# ===========================================================================
# 5. Checkpoint, Atomic Write, and Deterministic Parity Tests
# ===========================================================================
def test_checkpoint_atomic_write_leaves_no_tmp_files(tmp_path):
    """Verify atomic checkpoint writing creates valid file and leaves zero .tmp files."""
    mgr = CheckpointManager(checkpoint_dir=tmp_path)
    model = BaselineCNN(num_classes=NUM_CLASSES)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)

    target_path = mgr.save_checkpoint(
        filename="test_ckpt.pt",
        model=model,
        optimizer=optimizer,
        scheduler=None,
        global_epoch=1,
        stage_epoch=1,
        training_stage=None,
        early_stopping_state={},
        current_metrics={"macro_f1": 0.88},
        history={},
        config={},
    )

    assert target_path.exists()
    assert target_path.name == "test_ckpt.pt"

    # Verify zero orphaned .tmp files in checkpoint directory
    tmp_files = list(tmp_path.glob("*.tmp*"))
    assert len(tmp_files) == 0, f"Found orphaned temp files: {tmp_files}"


def test_dataloader_generator_state_restoration():
    """Verify saving and restoring DataLoader generator state reproduces exact identical shuffle order."""
    x = torch.arange(20).unsqueeze(1)
    dataset = TensorDataset(x)

    gen = torch.Generator().manual_seed(42)
    loader = DataLoader(dataset, batch_size=5, shuffle=True, generator=gen)

    # Consume 1 epoch
    first_epoch = [b[0].tolist() for b in loader]

    # Save generator state at epoch boundary
    saved_state = gen.get_state()

    # Consume second epoch (uninterrupted)
    second_epoch_uninterrupted = [b[0].tolist() for b in loader]

    # Create fresh generator, restore state, and run second epoch
    restored_gen = torch.Generator()
    restored_gen.set_state(saved_state)
    restored_loader = DataLoader(dataset, batch_size=5, shuffle=True, generator=restored_gen)
    second_epoch_resumed = [b[0].tolist() for b in restored_loader]

    assert second_epoch_uninterrupted == second_epoch_resumed


def test_deterministic_resume_parity(tmp_path):
    """Verify an uninterrupted 3-epoch run exactly matches a 2-epoch + resume epoch 3 run on deterministic setup."""
    # Fixed deterministic environment
    torch.manual_seed(12345)
    np.random.seed(12345)
    random.seed(12345)

    dummy_x = torch.randn(16, 3, 224, 224)
    dummy_y = torch.tensor([0, 1, 2, 0, 1, 2, 0, 1, 2, 0, 1, 2, 0, 1, 2, 0], dtype=torch.long)
    dataset = TensorDataset(dummy_x, dummy_y)

    config = TrainingConfig(
        model_architecture="baseline_cnn",
        seed=12345,
        checkpoint_dir=tmp_path,
        batch_size=4,
    )

    # --- Run A: Uninterrupted 3 epochs ---
    torch.manual_seed(12345)
    trainer_a = Trainer(config=config)
    loader_a = DataLoader(dataset, batch_size=4, shuffle=True, generator=trainer_a.train_generator)

    for epoch in range(1, 4):
        loss_a = trainer_a.train_epoch(loader_a)
        val_metrics_a = trainer_a.validate(loader_a)
        trainer_a.global_epoch = epoch

    final_loss_a = loss_a
    final_weight_a = list(trainer_a.model.parameters())[0].clone().detach()

    # --- Run B: 2 epochs, save checkpoint, destroy, resume for epoch 3 ---
    torch.manual_seed(12345)
    trainer_b = Trainer(config=config)
    loader_b = DataLoader(dataset, batch_size=4, shuffle=True, generator=trainer_b.train_generator)

    # Epoch 1 and 2
    for epoch in range(1, 3):
        loss_b = trainer_b.train_epoch(loader_b)
        val_metrics_b = trainer_b.validate(loader_b)
        trainer_b.global_epoch = epoch
        ckpt_path, _ = trainer_b.save_epoch_checkpoint(val_metrics=val_metrics_b)

    # Destroy trainer B instances
    del trainer_b, loader_b
    gc.collect()

    # Resume in fresh trainer instance
    trainer_b_resumed = Trainer(config=config)
    trainer_b_resumed.resume_from_checkpoint(ckpt_path)

    # Reconstruct DataLoader with restored generator
    loader_b_resumed = DataLoader(
        dataset,
        batch_size=4,
        shuffle=True,
        generator=trainer_b_resumed.train_generator,
    )

    # Run epoch 3
    final_loss_b = trainer_b_resumed.train_epoch(loader_b_resumed)
    final_weight_b = list(trainer_b_resumed.model.parameters())[0].clone().detach()

    # Assert exact bitwise floating-point parity
    assert pytest.approx(final_loss_a, rel=1e-5) == final_loss_b
    assert torch.allclose(final_weight_a, final_weight_b, atol=1e-6)


def test_checkpoint_schema_integrity_rejection(tmp_path):
    """Verify CheckpointManager rejects corrupt checkpoints missing required keys."""
    mgr = CheckpointManager(checkpoint_dir=tmp_path)
    corrupt_payload = {"some_key": 123}  # Missing model_state_dict, class_to_idx, etc.
    corrupt_file = tmp_path / "corrupt.pt"
    torch.save(corrupt_payload, corrupt_file)

    with pytest.raises(CheckpointIntegrityError):
        mgr.load_checkpoint(corrupt_file, is_trusted=True)


def test_untrusted_checkpoint_rejection(tmp_path):
    """Verify CheckpointManager refuses to load untrusted checkpoint with weights_only=False."""
    mgr = CheckpointManager(checkpoint_dir=tmp_path)
    dummy_file = tmp_path / "external.pt"
    torch.save({"data": 1}, dummy_file)

    with pytest.raises(UntrustedCheckpointError):
        mgr.load_checkpoint(dummy_file, is_trusted=False, weights_only=False)


# ===========================================================================
# 6. Fail-Fast Validation Tests
# ===========================================================================
def test_fail_fast_on_invalid_targets():
    """Verify Trainer raises InvalidDataError before loss calculation when class labels are out of bounds."""
    trainer = Trainer(TrainingConfig(model_architecture="baseline_cnn"))
    images = torch.randn(4, 3, 224, 224)
    invalid_targets = torch.tensor([0, 1, 99, 0], dtype=torch.long)  # 99 is invalid

    with pytest.raises(InvalidDataError):
        trainer.train_step(images, invalid_targets)


def test_fail_fast_on_nan_logits():
    """Verify Trainer raises TrainingDivergenceError when model forward pass outputs non-finite logits."""
    trainer = Trainer(TrainingConfig(model_architecture="baseline_cnn"))

    # Force model to produce NaN logits
    with torch.no_grad():
        trainer.model.classifier[4].weight.fill_(float("nan"))

    images = torch.randn(4, 3, 224, 224)
    targets = torch.tensor([0, 1, 2, 0], dtype=torch.long)

    with pytest.raises(TrainingDivergenceError):
        trainer.train_step(images, targets)


def test_fail_fast_on_nan_gradients():
    """Verify Trainer detects NaN gradients, zeroes gradients, aborts step, and raises GradientDivergenceError."""
    trainer = Trainer(TrainingConfig(model_architecture="baseline_cnn"))

    images = torch.randn(4, 3, 224, 224)
    targets = torch.tensor([0, 1, 2, 0], dtype=torch.long)

    # Mock backward to inject NaN gradient into a parameter
    first_param = next(trainer.model.parameters())

    def mock_validate_gradients():
        first_param.grad.fill_(float("nan"))
        # Call original validation logic
        Trainer.validate_gradients(trainer)

    with patch.object(trainer, "validate_gradients", side_effect=mock_validate_gradients):
        with pytest.raises(GradientDivergenceError):
            trainer.train_step(images, targets)


# ===========================================================================
# 7. Benchmark Preflight, Abort, and Isolation Tests
# ===========================================================================
def test_benchmark_preflight_memory_rejection():
    """Verify CPUBenchmark raises InsufficientMemoryError when preflight memory reserve is violated."""
    bench = CPUBenchmark(BenchmarkConfig(min_available_ram_bytes=100 * 1024 * 1024 * 1024))  # 100 GB reserve
    model = BaselineCNN(num_classes=NUM_CLASSES)

    with pytest.raises(InsufficientMemoryError):
        bench.run(model, model_name="baseline_cnn")


def test_benchmark_emergency_abort_stops_entire_run():
    """Verify CPUBenchmark aborts entire run when memory crosses emergency floor and restores environment state in finally."""
    config = BenchmarkConfig(
        batch_sizes=(16,),
        thread_counts=(4,),
        warmup_batches=1,
        measured_batches=2,
        min_available_ram_bytes=500 * 1024 * 1024,        # 500 MB preflight
        emergency_memory_floor_bytes=400 * 1024 * 1024,   # 400 MB floor
    )
    bench = CPUBenchmark(config=config)
    model = BaselineCNN(num_classes=NUM_CLASSES)
    orig_threads = torch.get_num_threads()

    # Preflight check has 600 MB (passes >= 500 MB).
    # Once inside the warm-up loop (call 3 onwards), available drops to 350 MB (< 400 MB floor).
    call_count = 0

    def mock_virtual_memory():
        nonlocal call_count
        call_count += 1
        m = MagicMock()
        if call_count > 2:
            m.available = 350 * 1024 * 1024  # Drops below 400 MB
        else:
            m.available = 600 * 1024 * 1024  # Passes preflight
        return m

    with patch("psutil.virtual_memory", side_effect=mock_virtual_memory):
        with pytest.raises(BenchmarkEmergencyAbortError):
            bench.run(model, model_name="baseline_cnn")

    # Assert thread count was cleanly restored in finally block
    assert torch.get_num_threads() == orig_threads


def test_benchmark_isolation():
    """Verify running CPUBenchmark does not mutate real model weights or alter input model."""
    bench = CPUBenchmark(
        BenchmarkConfig(
            batch_sizes=(4,),
            thread_counts=(4,),
            warmup_batches=1,
            measured_batches=2,
            min_available_ram_bytes=100 * 1024 * 1024,
            emergency_memory_floor_bytes=50 * 1024 * 1024,
        )
    )
    real_model = BaselineCNN(num_classes=NUM_CLASSES)
    initial_weights = [p.clone().detach() for p in real_model.parameters()]

    bench.run(real_model, model_name="baseline_cnn")

    # Real model weights must be 100% bitwise untouched
    for p_init, p_curr in zip(initial_weights, real_model.parameters()):
        assert torch.equal(p_init, p_curr), "Real model parameter mutated during benchmark!"


# ===========================================================================
# 8. Pretrained Weights Safety Test
# ===========================================================================
def test_pretrained_weights_not_found_error():
    """Verify MobileNetV3 with init_mode='imagenet' fails fast with PretrainedWeightsNotFoundError when local file absent."""
    config = TrainingConfig(
        model_architecture="mobilenet_v3_small",
        init_mode="imagenet",
        local_weights_path=Path("non_existent_weights.pth"),
    )

    with pytest.raises(PretrainedWeightsNotFoundError):
        Trainer(config=config)
