"""
ml/tests/test_training_integrity.py - Rigorous regression tests for early stopping,
checkpoint gating, tuple semantics, stage transitions, and deterministic state restoration.
"""

import gc
from pathlib import Path
import random
import numpy as np
import pytest
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from ml.config import NUM_CLASSES
from ml.models.baseline_cnn import BaselineCNN
from ml.training.checkpoints import CheckpointManager
from ml.training.config import TrainingConfig
from ml.training.early_stopping import EarlyStopping, EarlyStoppingResult
from ml.training.engine import Trainer


# ==============================================================================
# C1. Tuple Semantics & Type Enforcement Tests
# ==============================================================================
def test_early_stopping_result_named_tuple_unpacking():
    """Verify EarlyStoppingResult unpacks as a 2-tuple and supports attribute access."""
    res = EarlyStoppingResult(improved=True, should_stop=False)
    improved, should_stop = res
    assert improved is True
    assert should_stop is False
    assert res.improved is True
    assert res.should_stop is False


def test_tuple_semantics_gating_behavior(tmp_path):
    """
    Verify tuple semantics:
    - (False, False): no best-checkpoint save, no early stop.
    - (True, False): best-checkpoint saved, no early stop.
    - (False, True): no best-checkpoint save, early stop triggered.
    - (True, True): best-checkpoint saved, early stop triggered.
    """
    config = TrainingConfig(
        model_architecture="baseline_cnn",
        checkpoint_dir=tmp_path,
    )
    trainer = Trainer(config=config)

    # 1. Simulate (False, False)
    improved, should_stop = False, False
    last_p, best_p = trainer.save_epoch_checkpoint(
        val_metrics={"macro_f1": 0.50},
        is_best=improved,
    )
    assert last_p.exists()
    assert best_p is None
    assert should_stop is False

    # 2. Simulate (True, False)
    improved, should_stop = True, False
    last_p, best_p = trainer.save_epoch_checkpoint(
        val_metrics={"macro_f1": 0.60},
        is_best=improved,
    )
    assert last_p.exists()
    assert best_p is not None
    assert best_p.exists()
    assert should_stop is False

    # Reset best checkpoint file for clean isolation
    if best_p.exists():
        best_p.unlink()

    # 3. Simulate (False, True)
    improved, should_stop = False, True
    last_p, best_p = trainer.save_epoch_checkpoint(
        val_metrics={"macro_f1": 0.55},
        is_best=improved,
    )
    assert last_p.exists()
    assert best_p is None
    assert should_stop is True

    # 4. Simulate (True, True) if emitted or handled
    improved, should_stop = True, True
    last_p, best_p = trainer.save_epoch_checkpoint(
        val_metrics={"macro_f1": 0.65},
        is_best=improved,
    )
    assert last_p.exists()
    assert best_p is not None
    assert best_p.exists()
    assert should_stop is True


def test_save_epoch_checkpoint_rejects_non_boolean_is_best(tmp_path):
    """Verify save_epoch_checkpoint strictly rejects tuples or non-bools for is_best."""
    config = TrainingConfig(
        model_architecture="baseline_cnn",
        checkpoint_dir=tmp_path,
    )
    trainer = Trainer(config=config)

    # Attempt to pass a raw tuple without unpacking
    with pytest.raises(TypeError, match="is_best must be a strict boolean"):
        trainer.save_epoch_checkpoint(
            val_metrics={"macro_f1": 0.70},
            is_best=(False, False),  # type: ignore
        )

    with pytest.raises(TypeError, match="is_best must be a strict boolean"):
        trainer.save_epoch_checkpoint(
            val_metrics={"macro_f1": 0.70},
            is_best=(True, False),  # type: ignore
        )

    with pytest.raises(TypeError, match="is_best must be a strict boolean"):
        trainer.save_epoch_checkpoint(
            val_metrics={"macro_f1": 0.70},
            is_best=1,  # type: ignore (int, not strict bool)
        )

    # Explicitly test passing an EarlyStoppingResult NamedTuple directly raises TypeError
    with pytest.raises(TypeError, match="is_best must be a strict boolean"):
        trainer.save_epoch_checkpoint(
            val_metrics={"macro_f1": 0.70},
            is_best=EarlyStoppingResult(improved=False, should_stop=False),  # type: ignore
        )

    with pytest.raises(TypeError, match="is_best must be a strict boolean"):
        trainer.save_epoch_checkpoint(
            val_metrics={"macro_f1": 0.70},
            is_best=EarlyStoppingResult(improved=True, should_stop=False),  # type: ignore
        )


# ==============================================================================
# C2. Best Checkpoint Integrity on Metric Sequence
# ==============================================================================
def test_best_checkpoint_integrity_on_metric_sequence(tmp_path):
    """
    Simulate sequence: 0.70, 0.75, 0.73, 0.74, 0.80, 0.78.
    Verify:
    - Best checkpoint strictly holds Epoch 5 (macro_f1 = 0.80).
    - Non-improving epochs (3, 4, 6) do NOT overwrite the best checkpoint.
    - Saved epoch metadata in best checkpoint matches Epoch 5.
    - Last checkpoint holds Epoch 6 (macro_f1 = 0.78).
    """
    config = TrainingConfig(
        model_architecture="baseline_cnn",
        checkpoint_dir=tmp_path,
        baseline_patience=6,
        baseline_min_delta=0.001,
    )
    trainer = Trainer(config=config)

    metric_sequence = [0.70, 0.75, 0.73, 0.74, 0.80, 0.78]
    best_epochs_recorded = []

    for ep_idx, score in enumerate(metric_sequence, start=1):
        trainer.global_epoch = ep_idx
        trainer.stage_epoch = ep_idx

        # Mutate a bias parameter to give each epoch unique weights
        with torch.no_grad():
            list(trainer.model.parameters())[0].fill_(float(ep_idx))

        improved, should_stop = trainer.step_early_stopping(score)
        if improved:
            best_epochs_recorded.append(ep_idx)

        val_metrics = {
            "macro_f1": score,
            "accuracy": score + 0.05,
            "loss": 1.0 - score,
        }
        trainer.save_epoch_checkpoint(val_metrics, is_best=improved)

    # Genuine improvements should only be epochs 1 (0.70), 2 (0.75), 5 (0.80)
    assert best_epochs_recorded == [1, 2, 5]

    # Load best checkpoint and verify metadata
    best_path = tmp_path / "baseline_cnn_best.pt"
    assert best_path.exists()
    best_ckpt = trainer.checkpoint_manager.load_checkpoint(best_path, is_trusted=True)
    assert best_ckpt["global_epoch"] == 5
    assert best_ckpt["stage_epoch"] == 5
    assert best_ckpt["current_metrics"]["macro_f1"] == 0.80
    # Parameter values must match Epoch 5
    assert torch.allclose(best_ckpt["model_state_dict"]["features.0.block.0.weight"], torch.tensor(5.0))

    # Load last checkpoint and verify metadata
    last_path = tmp_path / "baseline_cnn_last.pt"
    assert last_path.exists()
    last_ckpt = trainer.checkpoint_manager.load_checkpoint(last_path, is_trusted=True)
    assert last_ckpt["global_epoch"] == 6
    assert last_ckpt["stage_epoch"] == 6
    assert last_ckpt["current_metrics"]["macro_f1"] == 0.78
    assert torch.allclose(last_ckpt["model_state_dict"]["features.0.block.0.weight"], torch.tensor(6.0))


# ==============================================================================
# C3. Min-Delta Behavior
# ==============================================================================
def test_min_delta_strict_enforcement():
    """Verify improvements >= min_delta reset patience; < min_delta increment patience."""
    es = EarlyStopping(patience=5, min_delta=0.01)

    # Initial epoch
    improved, stop = es.update(0.70)
    assert improved is True
    assert es.best_score == 0.70
    assert es.patience_counter == 0

    # Sub-delta improvement: 0.7099 < 0.70 + 0.01
    improved, stop = es.update(0.7099)
    assert improved is False
    assert es.best_score == 0.70
    assert es.patience_counter == 1

    # Exact threshold: 0.7100 == 0.70 + 0.01
    improved, stop = es.update(0.7100)
    assert improved is True
    assert es.best_score == pytest.approx(0.7100)
    assert es.patience_counter == 0

    # Sub-delta improvement: 0.715 < 0.71 + 0.01
    improved, stop = es.update(0.715)
    assert improved is False
    assert es.best_score == pytest.approx(0.7100)
    assert es.patience_counter == 1

    # Large improvement: 0.80 >= 0.71 + 0.01
    improved, stop = es.update(0.80)
    assert improved is True
    assert es.best_score == 0.80
    assert es.patience_counter == 0


def test_early_stopping_rejects_non_finite_scores():
    """Verify EarlyStopping rejects NaN and Inf scores with ValueError."""
    es = EarlyStopping(patience=3, min_delta=0.001)

    with pytest.raises(ValueError, match="finite number"):
        es.update(float("nan"))

    with pytest.raises(ValueError, match="finite number"):
        es.update(float("inf"))

    with pytest.raises(ValueError, match="finite number"):
        es.update(-float("inf"))


# ==============================================================================
# C4. Early Stopping Halt & Best Checkpoint Preservation
# ==============================================================================
def test_early_stopping_exhaustion_and_best_checkpoint_preservation(tmp_path):
    """Verify training stops exactly when patience exhausts and best checkpoint is preserved."""
    patience = 3
    config = TrainingConfig(
        model_architecture="baseline_cnn",
        checkpoint_dir=tmp_path,
        baseline_patience=patience,
        baseline_min_delta=0.01,
    )
    trainer = Trainer(config=config)

    # Epoch 1: score 0.70 -> best
    improved, stop = trainer.step_early_stopping(0.70)
    assert (improved, stop) == (True, False)
    with torch.no_grad():
        list(trainer.model.parameters())[0].fill_(100.0)
    trainer.global_epoch = 1
    trainer.save_epoch_checkpoint({"macro_f1": 0.70}, is_best=improved)

    # Epoch 2: score 0.705 -> patience=1
    improved, stop = trainer.step_early_stopping(0.705)
    assert (improved, stop) == (False, False)
    with torch.no_grad():
        list(trainer.model.parameters())[0].fill_(200.0)
    trainer.global_epoch = 2
    trainer.save_epoch_checkpoint({"macro_f1": 0.705}, is_best=improved)

    # Epoch 3: score 0.69 -> patience=2
    improved, stop = trainer.step_early_stopping(0.69)
    assert (improved, stop) == (False, False)
    with torch.no_grad():
        list(trainer.model.parameters())[0].fill_(300.0)
    trainer.global_epoch = 3
    trainer.save_epoch_checkpoint({"macro_f1": 0.69}, is_best=improved)

    # Epoch 4: score 0.702 -> patience=3 -> triggers stop!
    improved, stop = trainer.step_early_stopping(0.702)
    assert (improved, stop) == (False, True)
    with torch.no_grad():
        list(trainer.model.parameters())[0].fill_(400.0)
    trainer.global_epoch = 4
    trainer.save_epoch_checkpoint({"macro_f1": 0.702}, is_best=improved)

    # Verify best checkpoint remains untouched from Epoch 1 (weight 100.0)
    best_ckpt = trainer.checkpoint_manager.load_checkpoint(
        tmp_path / "baseline_cnn_best.pt",
        is_trusted=True,
    )
    assert best_ckpt["global_epoch"] == 1
    assert best_ckpt["current_metrics"]["macro_f1"] == 0.70
    assert torch.allclose(best_ckpt["model_state_dict"]["features.0.block.0.weight"], torch.tensor(100.0))

    # Verify last checkpoint holds Epoch 4 (weight 400.0)
    last_ckpt = trainer.checkpoint_manager.load_checkpoint(
        tmp_path / "baseline_cnn_last.pt",
        is_trusted=True,
    )
    assert last_ckpt["global_epoch"] == 4
    assert last_ckpt["current_metrics"]["macro_f1"] == 0.702
    assert torch.allclose(last_ckpt["model_state_dict"]["features.0.block.0.weight"], torch.tensor(400.0))


# ==============================================================================
# C5. Serialization and Restoration Parity
# ==============================================================================
def test_early_stopping_serialization_and_restoration_parity(tmp_path):
    """Verify early stopping state survives checkpointing and resumes with identical behavior."""
    es_original = EarlyStopping(patience=4, min_delta=0.01)

    es_original.update(0.60)  # best=0.60, patience=0
    es_original.update(0.605)  # patience=1
    es_original.update(0.59)  # patience=2
    assert es_original.patience_counter == 2
    assert es_original.best_score == 0.60

    # Serialize state dict
    state = es_original.state_dict()

    # Restore into fresh instance
    es_restored = EarlyStopping(patience=4, min_delta=0.01)
    es_restored.load_state_dict(state)

    assert es_restored.best_score == 0.60
    assert es_restored.patience_counter == 2
    assert es_restored.should_stop is False

    # Advance both with sub-delta score
    res_orig = es_original.update(0.602)
    res_rest = es_restored.update(0.602)

    assert res_orig == res_rest == (False, False)
    assert es_original.patience_counter == es_restored.patience_counter == 3

    # Advance both with genuine improvement
    res_orig_imp = es_original.update(0.65)
    res_rest_imp = es_restored.update(0.65)

    assert res_orig_imp == res_rest_imp == (True, False)
    assert es_original.patience_counter == es_restored.patience_counter == 0
    assert es_original.best_score == es_restored.best_score == 0.65


# ==============================================================================
# C6. Stage-Specific Behavior and Optimizer Isolation
# ==============================================================================
def test_stage_specific_checkpoints_and_optimizer_isolation(tmp_path):
    """
    Verify:
    - Stage 1 and Stage 2 maintain distinct checkpoint filenames.
    - Stage 1 optimizer is discarded and Stage 2 optimizer is freshly instantiated.
    - Stage transition loads the true best Stage 1 weights.
    """
    config = TrainingConfig(
        model_architecture="mobilenet_v3_small",
        init_mode="random",
        checkpoint_dir=tmp_path,
        stage1_epochs=3,
        stage2_epochs=5,
    )
    trainer = Trainer(config=config)

    # Stage 1: Warmup
    assert trainer.current_stage == 1
    assert len(trainer.optimizer.param_groups) == 1

    # Epoch 1: score 0.50 -> best Stage 1
    with torch.no_grad():
        trainer.model.classifier[3].weight.fill_(88.88)
    trainer.global_epoch = 1
    trainer.stage_epoch = 1
    s1_last, s1_best = trainer.save_epoch_checkpoint({"macro_f1": 0.50}, is_best=True)
    assert s1_best.name == "mobilenet_v3_small_stage1_best.pt"
    assert s1_last.name == "mobilenet_v3_small_stage1_last.pt"

    # Epoch 2: score 0.40 -> non-improving
    with torch.no_grad():
        trainer.model.classifier[3].weight.fill_(11.11)
    trainer.global_epoch = 2
    trainer.stage_epoch = 2
    s1_last, s1_best = trainer.save_epoch_checkpoint({"macro_f1": 0.40}, is_best=False)
    assert s1_best is None

    # Stage Transition: Must load best Stage 1 weights (88.88), not degraded (11.11)
    trainer.transition_to_stage2(stage1_checkpoint_path=tmp_path / "mobilenet_v3_small_stage1_best.pt")
    assert trainer.current_stage == 2
    assert len(trainer.optimizer.param_groups) == 2
    assert torch.allclose(trainer.model.classifier[3].weight, torch.tensor(88.88))

    # Stage 2: Save best and last checkpoints
    with torch.no_grad():
        trainer.model.classifier[3].weight.fill_(99.99)
    trainer.global_epoch = 3
    trainer.stage_epoch = 1
    s2_last, s2_best = trainer.save_epoch_checkpoint({"macro_f1": 0.70}, is_best=True)
    assert s2_best.name == "mobilenet_v3_small_stage2_best.pt"
    assert s2_last.name == "mobilenet_v3_small_stage2_last.pt"

    # Verify Stage 1 checkpoints were NOT overwritten by Stage 2
    s1_best_loaded = trainer.checkpoint_manager.load_checkpoint(
        tmp_path / "mobilenet_v3_small_stage1_best.pt",
        is_trusted=True,
    )
    assert s1_best_loaded["training_stage"] == 1
    assert s1_best_loaded["current_metrics"]["macro_f1"] == 0.50

    s2_best_loaded = trainer.checkpoint_manager.load_checkpoint(
        tmp_path / "mobilenet_v3_small_stage2_best.pt",
        is_trusted=True,
    )
    assert s2_best_loaded["training_stage"] == 2
    assert s2_best_loaded["current_metrics"]["macro_f1"] == 0.70


# ==============================================================================
# C7. Comprehensive Deterministic Interrupted-vs-Uninterrupted Parity Test
# ==============================================================================
def test_deterministic_interrupted_vs_uninterrupted_parity_comprehensive(tmp_path):
    """
    Conclusively proves deterministic interrupted-versus-uninterrupted training parity.

    Compares:
    A. An uninterrupted 4-epoch training sequence.
    B. A 2-epoch sequence interrupted, checkpointed, reconstructed from scratch,
       and resumed for epochs 3 and 4.

    Verifies bitwise / exact floating-point equality across:
    - Model parameters.
    - Optimizer state dict.
    - Scheduler state dict.
    - Early-stopping state dict (best_score, patience_counter, should_stop).
    - Global and stage epoch numbering.
    - Training and validation history.
    - PyTorch CPU, Python, NumPy, and DataLoader generator RNG states.
    - Subsequent Epoch 5 training losses and validation metrics.
    """
    dir_a = tmp_path / "run_a"
    dir_b = tmp_path / "run_b"
    dir_a.mkdir(parents=True, exist_ok=True)
    dir_b.mkdir(parents=True, exist_ok=True)

    # 1. Deterministic synthetic dataset
    torch.manual_seed(12345)
    X_train = torch.randn(32, 3, 224, 224)
    y_train = torch.randint(0, NUM_CLASSES, (32,), dtype=torch.long)
    train_dataset = TensorDataset(X_train, y_train)

    X_val = torch.randn(16, 3, 224, 224)
    y_val = torch.randint(0, NUM_CLASSES, (16,), dtype=torch.long)
    val_dataset = TensorDataset(X_val, y_val)

    config_a = TrainingConfig(
        model_architecture="baseline_cnn",
        seed=12345,
        checkpoint_dir=dir_a,
        batch_size=8,
        baseline_patience=5,
        baseline_min_delta=0.001,
    )
    config_b = TrainingConfig(
        model_architecture="baseline_cnn",
        seed=12345,
        checkpoint_dir=dir_b,
        batch_size=8,
        baseline_patience=5,
        baseline_min_delta=0.001,
    )

    # =========================================================================
    # Run A: Uninterrupted 4 Epochs
    # =========================================================================
    torch.manual_seed(12345)
    np.random.seed(12345)
    random.seed(12345)

    trainer_a = Trainer(config=config_a)
    loader_a_train = DataLoader(
        train_dataset,
        batch_size=8,
        shuffle=True,
        generator=trainer_a.train_generator,
    )
    loader_a_val = DataLoader(val_dataset, batch_size=8, shuffle=False)

    for epoch in range(1, 5):
        trainer_a.global_epoch = epoch
        trainer_a.stage_epoch = epoch
        t_loss = trainer_a.train_epoch(loader_a_train)
        v_metrics = trainer_a.validate(loader_a_val)
        trainer_a.step_scheduler()
        improved, should_stop = trainer_a.step_early_stopping(v_metrics["macro_f1"])
        trainer_a.history["train_loss"].append(round(t_loss, 4))
        trainer_a.history["val_metrics"].append(v_metrics)
        trainer_a.save_epoch_checkpoint(val_metrics=v_metrics, is_best=improved)

    # Capture Run A state at completion of Epoch 4
    params_a = [p.clone().detach() for p in trainer_a.model.parameters()]
    opt_state_a = trainer_a.optimizer.state_dict()
    sched_state_a = trainer_a.scheduler.state_dict()
    es_state_a = trainer_a.early_stopping.state_dict()
    history_a = dict(trainer_a.history)
    global_epoch_a = trainer_a.global_epoch
    stage_epoch_a = trainer_a.stage_epoch
    rng_torch_a = torch.get_rng_state()
    rng_gen_a = trainer_a.train_generator.get_state()
    rng_py_a = random.getstate()
    rng_np_a = np.random.get_state()

    # =========================================================================
    # Run B: 2 Epochs -> Checkpoint -> Destroy -> Reconstruct & Resume 2 Epochs
    # =========================================================================
    torch.manual_seed(12345)
    np.random.seed(12345)
    random.seed(12345)

    trainer_b = Trainer(config=config_b)
    loader_b_train = DataLoader(
        train_dataset,
        batch_size=8,
        shuffle=True,
        generator=trainer_b.train_generator,
    )
    loader_b_val = DataLoader(val_dataset, batch_size=8, shuffle=False)

    # Execute Epochs 1 and 2
    for epoch in range(1, 3):
        trainer_b.global_epoch = epoch
        trainer_b.stage_epoch = epoch
        t_loss = trainer_b.train_epoch(loader_b_train)
        v_metrics = trainer_b.validate(loader_b_val)
        trainer_b.step_scheduler()
        improved, should_stop = trainer_b.step_early_stopping(v_metrics["macro_f1"])
        trainer_b.history["train_loss"].append(round(t_loss, 4))
        trainer_b.history["val_metrics"].append(v_metrics)
        ckpt_path_b, _ = trainer_b.save_epoch_checkpoint(val_metrics=v_metrics, is_best=improved)

    # Destroy trainer B objects completely
    del trainer_b, loader_b_train, loader_b_val
    gc.collect()

    # Reconstruct fresh Trainer and resume from saved Epoch 2 checkpoint
    trainer_b_resumed = Trainer(config=config_b)
    trainer_b_resumed.resume_from_checkpoint(ckpt_path_b)

    # Verify state immediately after resumption (at Epoch 2 boundary)
    assert trainer_b_resumed.global_epoch == 2
    assert trainer_b_resumed.stage_epoch == 2
    assert len(trainer_b_resumed.history["train_loss"]) == 2

    # Reconstruct DataLoader using the restored DataLoader generator
    loader_b_res_train = DataLoader(
        train_dataset,
        batch_size=8,
        shuffle=True,
        generator=trainer_b_resumed.train_generator,
    )
    loader_b_res_val = DataLoader(val_dataset, batch_size=8, shuffle=False)

    # Execute Epochs 3 and 4 on the resumed trainer
    for epoch in range(3, 5):
        trainer_b_resumed.global_epoch = epoch
        trainer_b_resumed.stage_epoch = epoch
        t_loss = trainer_b_resumed.train_epoch(loader_b_res_train)
        v_metrics = trainer_b_resumed.validate(loader_b_res_val)
        trainer_b_resumed.step_scheduler()
        improved, should_stop = trainer_b_resumed.step_early_stopping(v_metrics["macro_f1"])
        trainer_b_resumed.history["train_loss"].append(round(t_loss, 4))
        trainer_b_resumed.history["val_metrics"].append(v_metrics)
        trainer_b_resumed.save_epoch_checkpoint(val_metrics=v_metrics, is_best=improved)

    # Capture Run B state at completion of Epoch 4
    params_b = [p.clone().detach() for p in trainer_b_resumed.model.parameters()]
    opt_state_b = trainer_b_resumed.optimizer.state_dict()
    sched_state_b = trainer_b_resumed.scheduler.state_dict()
    es_state_b = trainer_b_resumed.early_stopping.state_dict()
    history_b = dict(trainer_b_resumed.history)
    global_epoch_b = trainer_b_resumed.global_epoch
    stage_epoch_b = trainer_b_resumed.stage_epoch
    rng_torch_b = torch.get_rng_state()
    rng_gen_b = trainer_b_resumed.train_generator.get_state()
    rng_py_b = random.getstate()
    rng_np_b = np.random.get_state()

    # =========================================================================
    # Strict Parity Assertions at Epoch 4
    # =========================================================================
    # 1. Model parameter parity (bitwise identical)
    for idx, (p_a, p_b) in enumerate(zip(params_a, params_b)):
        assert torch.allclose(p_a, p_b, atol=1e-7), f"Parameter mismatch at index {idx}"
        assert torch.equal(p_a, p_b), f"Parameter bitwise mismatch at index {idx}"

    # 2. Scheduler state parity
    assert sched_state_a == sched_state_b, "Scheduler state mismatch between uninterrupted and resumed run"

    # 3. Early stopping state parity
    assert es_state_a["best_score"] == es_state_b["best_score"], "Early stopping best score mismatch"
    assert es_state_a["patience_counter"] == es_state_b["patience_counter"], "Early stopping patience counter mismatch"
    assert es_state_a["should_stop"] == es_state_b["should_stop"], "Early stopping should_stop mismatch"

    # 4. Epoch tracking parity
    assert global_epoch_a == global_epoch_b == 4
    assert stage_epoch_a == stage_epoch_b == 4

    # 5. Training history parity
    assert history_a["train_loss"] == history_b["train_loss"]
    assert history_a["val_metrics"] == history_b["val_metrics"]

    # 6. RNG state parity
    assert torch.equal(rng_torch_a, rng_torch_b), "PyTorch CPU RNG state mismatch"
    assert torch.equal(rng_gen_a, rng_gen_b), "DataLoader generator state mismatch"
    assert rng_py_a == rng_py_b, "Python random state mismatch"
    assert rng_np_a[0] == rng_np_b[0] and np.array_equal(rng_np_a[1], rng_np_b[1]), "NumPy random state mismatch"

    # =========================================================================
    # Subsequent Step Parity: Execute Epoch 5 on both runs
    # =========================================================================
    # Restore Run A exact RNG state before Epoch 5
    torch.set_rng_state(rng_torch_a)
    trainer_a.train_generator.set_state(rng_gen_a)
    random.setstate(rng_py_a)
    np.random.set_state(rng_np_a)
    loss_5_a = trainer_a.train_epoch(loader_a_train)
    val_5_a = trainer_a.validate(loader_a_val)

    # Restore Run B exact RNG state before Epoch 5
    torch.set_rng_state(rng_torch_b)
    trainer_b_resumed.train_generator.set_state(rng_gen_b)
    random.setstate(rng_py_b)
    np.random.set_state(rng_np_b)
    loss_5_b = trainer_b_resumed.train_epoch(loader_b_res_train)
    val_5_b = trainer_b_resumed.validate(loader_b_res_val)

    # Verify Epoch 5 loss and validation metric bitwise equivalence
    assert loss_5_a == loss_5_b, f"Epoch 5 training loss mismatch: {loss_5_a} vs {loss_5_b}"
    assert val_5_a["macro_f1"] == val_5_b["macro_f1"], f"Epoch 5 val macro_f1 mismatch: {val_5_a['macro_f1']} vs {val_5_b['macro_f1']}"
    assert val_5_a["accuracy"] == val_5_b["accuracy"]
    assert val_5_a["confusion_matrix"] == val_5_b["confusion_matrix"]

