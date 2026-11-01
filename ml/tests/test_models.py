"""
ml/tests/test_models.py - Comprehensive architecture and configuration unit tests.

Validates:
- BaselineCNN construction, layer dimensions, parameter counts (405,539), and unnormalized logits.
- MobileNetV3-Small constructor with weights=None default and 3-class linear head.
- MobileNetV3-Small exact parameter count (1,520,931).
- Stage 1 and Stage 2 parameter freezing and unfreezing boundaries.
- Optimizer parameter groups containing exclusively trainable parameters with designated learning rates.
- BatchNorm evaluation mode enforcement and preservation of running statistics across train-mode passes.
- Universal acceptance of (B, 3, 224, 224) normalized input tensors across both models.
- Absence of softmax within models (raw logits returned).
"""

import inspect
import pytest
import torch
import torch.nn as nn

from ml.config import NUM_CLASSES
from ml.models.baseline_cnn import BaselineCNN, ConvBlock
from ml.models.mobilenet_v3 import (
    STAGE1_CLASSIFIER_LR,
    STAGE2_BACKBONE_LR,
    STAGE2_CLASSIFIER_LR,
    build_mobilenet_v3,
    configure_mobilenet_stage,
    count_mobilenet_parameters,
    enter_train_mode,
    freeze_batchnorm_running_stats,
    get_mobilenet_param_groups,
)


# ===========================================================================
# 1. Baseline CNN Tests
# ===========================================================================
def test_baseline_cnn_construction_and_output_shapes():
    """Verify Baseline CNN forward pass produces (B, NUM_CLASSES) finite logits."""
    model = BaselineCNN(num_classes=NUM_CLASSES)
    model.eval()

    dummy_input = torch.randn(2, 3, 224, 224)
    with torch.no_grad():
        output = model(dummy_input)

    assert output.shape == (2, 3)
    assert torch.isfinite(output).all()


def test_baseline_cnn_exact_parameter_count():
    """Verify total parameter count matches mathematical derivation (exactly 405,539)."""
    model = BaselineCNN(num_classes=3)
    total_params, trainable_params = model.count_parameters()

    assert (
        total_params == 405539
    ), f"Expected 405,539 total parameters, got {total_params}"
    assert (
        trainable_params == 405539
    ), f"Expected 405,539 trainable parameters, got {trainable_params}"

    counts = model.get_parameter_counts()
    assert counts["total"] == 405539
    assert counts["trainable"] == 405539
    assert counts["frozen"] == 0


def test_baseline_cnn_configurable_classes():
    """Verify Baseline CNN adapts to custom class counts."""
    # 5 classes
    model_5 = BaselineCNN(num_classes=5)
    dummy_input = torch.randn(1, 3, 224, 224)
    out_5 = model_5(dummy_input)
    assert out_5.shape == (1, 5)

    # Invalid class count raises ValueError
    with pytest.raises(ValueError):
        BaselineCNN(num_classes=0)

    with pytest.raises(ValueError):
        BaselineCNN(num_classes=-1)


def test_baseline_cnn_no_softmax():
    """Verify model outputs raw unnormalized logits (not constrained to [0, 1] or summing to 1.0)."""
    model = BaselineCNN(num_classes=3)
    model.eval()

    dummy_input = torch.randn(4, 3, 224, 224)
    with torch.no_grad():
        logits = model(dummy_input)

    # Softmax sums across class dimension would be 1.0; raw logits generally do not sum to 1.0
    row_sums = logits.sum(dim=-1)
    assert not torch.allclose(row_sums, torch.ones_like(row_sums), atol=1e-3)


def test_baseline_cnn_classifier_dropout_rates():
    """Verify Baseline CNN classifier head has exact approved Dropout probabilities (0.4 and 0.2)."""
    model = BaselineCNN(num_classes=3)

    # Expected sequential sequence:
    # 0: Dropout(p=0.4)
    # 1: Linear(256, 64)
    # 2: ReLU
    # 3: Dropout(p=0.2)
    # 4: Linear(64, 3)
    assert len(model.classifier) == 5

    assert isinstance(model.classifier[0], nn.Dropout)
    assert model.classifier[0].p == 0.4

    assert isinstance(model.classifier[1], nn.Linear)
    assert model.classifier[1].in_features == 256
    assert model.classifier[1].out_features == 64

    assert isinstance(model.classifier[2], nn.ReLU)

    assert isinstance(model.classifier[3], nn.Dropout)
    assert model.classifier[3].p == 0.2

    assert isinstance(model.classifier[4], nn.Linear)
    assert model.classifier[4].in_features == 64
    assert model.classifier[4].out_features == 3


# ===========================================================================
# 2. MobileNetV3-Small Tests
# ===========================================================================
def test_mobilenet_v3_construction_default_weights_none():
    """Verify MobileNetV3 defaults to weights=None and does not download pretrained weights."""
    # Verify signature default argument
    sig = inspect.signature(build_mobilenet_v3)
    assert sig.parameters["pretrained"].default is False

    # Instantiate model without network activity
    model = build_mobilenet_v3(num_classes=3, pretrained=False)
    model.eval()

    dummy_input = torch.randn(2, 3, 224, 224)
    with torch.no_grad():
        output = model(dummy_input)

    assert output.shape == (2, 3)
    assert torch.isfinite(output).all()


def test_mobilenet_v3_exact_parameter_count():
    """Verify parameter count matches mathematical derivation (exactly 1,520,931)."""
    model = build_mobilenet_v3(num_classes=3, pretrained=False)
    total_params, trainable_params = count_mobilenet_parameters(model)

    assert (
        total_params == 1520931
    ), f"Expected 1,520,931 total parameters, got {total_params}"
    assert (
        trainable_params == 1520931
    ), "Initially all parameters should be trainable"


def test_mobilenet_v3_stage1_freezing():
    """Verify Stage 1 freezes all backbone parameters and leaves classifier trainable."""
    model = build_mobilenet_v3(num_classes=3, pretrained=False)
    configure_mobilenet_stage(model, stage=1)

    # Assert backbone parameters are frozen
    for p in model.features.parameters():
        assert not p.requires_grad, "Backbone parameter unexpectedly unfrozen!"

    # Assert classifier parameters are trainable
    for p in model.classifier.parameters():
        assert p.requires_grad, "Classifier parameter unexpectedly frozen!"

    # Expected trainable parameters in classifier:
    # classifier[0]: Linear(576, 1024) -> 576 * 1024 + 1024 = 590,848
    # classifier[3]: Linear(1024, 3)   -> 1024 * 3 + 3       = 3,075
    # Total trainable = 593,923
    total, trainable = count_mobilenet_parameters(model)
    assert total == 1520931
    assert trainable == 593923
    assert total - trainable == 927008


def test_mobilenet_v3_stage1_param_groups():
    """Verify Stage 1 optimizer parameter group contains only classifier parameters with lr=1e-3."""
    model = build_mobilenet_v3(num_classes=3, pretrained=False)
    configure_mobilenet_stage(model, stage=1)

    groups = get_mobilenet_param_groups(model, stage=1)
    assert len(groups) == 1
    group = groups[0]

    assert group["name"] == "classifier"
    assert group["lr"] == STAGE1_CLASSIFIER_LR
    assert group["weight_decay"] == 1e-4

    group_params = set(group["params"])
    trainable_params = set(p for p in model.parameters() if p.requires_grad)
    assert (
        group_params == trainable_params
    ), "Group parameters do not match trainable parameters!"

    # Zero frozen parameters in group
    for p in group_params:
        assert p.requires_grad


def test_mobilenet_v3_stage2_freezing():
    """Verify Stage 2 keeps features[:9] frozen, unfreezes features[9:], and keeps classifier trainable."""
    model = build_mobilenet_v3(num_classes=3, pretrained=False)
    configure_mobilenet_stage(model, stage=2)

    # Blocks 0..8 must remain frozen
    for i in range(9):
        for p in model.features[i].parameters():
            assert (
                not p.requires_grad
            ), f"Feature block {i} unexpectedly unfrozen!"

    # Blocks 9..12 must be trainable
    for i in range(9, len(model.features)):
        for p in model.features[i].parameters():
            assert p.requires_grad, f"Feature block {i} unexpectedly frozen!"

    # Classifier must be trainable
    for p in model.classifier.parameters():
        assert p.requires_grad, "Classifier parameter unexpectedly frozen!"


def test_mobilenet_v3_stage2_param_groups():
    """Verify Stage 2 optimizer parameter groups have differential learning rates."""
    model = build_mobilenet_v3(num_classes=3, pretrained=False)
    configure_mobilenet_stage(model, stage=2)

    groups = get_mobilenet_param_groups(model, stage=2)
    assert len(groups) == 2

    backbone_group = groups[0]
    classifier_group = groups[1]

    assert backbone_group["name"] == "backbone_high_level"
    assert backbone_group["lr"] == STAGE2_BACKBONE_LR  # 1e-5
    assert (
        len(backbone_group["params"]) > 0
    ), "Backbone group has zero parameters!"

    assert classifier_group["name"] == "classifier"
    assert classifier_group["lr"] == STAGE2_CLASSIFIER_LR  # 1e-4
    assert (
        len(classifier_group["params"]) > 0
    ), "Classifier group has zero parameters!"

    # Verify parameters in backbone group belong exclusively to features[9:]
    high_level_features_params = set(model.features[9:].parameters())
    for p in backbone_group["params"]:
        assert p.requires_grad
        assert p in high_level_features_params

    # Verify parameters in classifier group belong exclusively to classifier
    classifier_params = set(model.classifier.parameters())
    for p in classifier_group["params"]:
        assert p.requires_grad
        assert p in classifier_params


def test_mobilenet_v3_batchnorm_running_stats_remain_unchanged():
    """
    CRITICAL TEST: Verifies that enter_train_mode / freeze_batchnorm_running_stats
    prevents BatchNorm running_mean and running_var from changing during a training-mode forward pass.
    """
    model = build_mobilenet_v3(num_classes=3, pretrained=False)
    configure_mobilenet_stage(model, stage=1)

    # Set to train mode with BatchNorm evaluation policy applied
    enter_train_mode(model, stage=1)

    # Verify classifier is in training mode (Dropout active)
    assert model.classifier.training is True

    # Identify a BatchNorm2d module in the backbone
    bn_module = None
    for m in model.features.modules():
        if isinstance(m, nn.BatchNorm2d):
            bn_module = m
            break
    assert (
        bn_module is not None
    ), "No BatchNorm2d module discovered in backbone!"
    assert (
        bn_module.training is False
    ), "BatchNorm module must be in eval mode!"

    # Initialize running statistics with distinctive constants
    bn_module.running_mean.fill_(0.5)
    bn_module.running_var.fill_(2.0)

    mean_initial = bn_module.running_mean.clone()
    var_initial = bn_module.running_var.clone()

    # Execute training-mode forward pass with dynamic, high-variance batch
    dummy_input = torch.randn(8, 3, 224, 224) * 10.0 + 5.0
    _ = model(dummy_input)

    # Assert running statistics have NOT mutated
    assert torch.equal(
        bn_module.running_mean, mean_initial
    ), "running_mean mutated despite freeze_batchnorm_running_stats!"
    assert torch.equal(
        bn_module.running_var, var_initial
    ), "running_var mutated despite freeze_batchnorm_running_stats!"

    # Contrast check: If we put BatchNorm in train mode, it MUST update running statistics
    bn_module.train()
    _ = model(dummy_input)
    assert not torch.equal(
        bn_module.running_mean, mean_initial
    ), "Control assertion failed: BatchNorm in train mode failed to update running_mean"


def test_invalid_stage_raises_value_error():
    """Verify invalid stage numbers raise ValueError across configuration utilities."""
    model = build_mobilenet_v3(num_classes=3, pretrained=False)

    with pytest.raises(ValueError):
        configure_mobilenet_stage(model, stage=0)

    with pytest.raises(ValueError):
        configure_mobilenet_stage(model, stage=3)

    with pytest.raises(ValueError):
        enter_train_mode(model, stage=0)

    with pytest.raises(ValueError):
        get_mobilenet_param_groups(model, stage=0)


# ===========================================================================
# 3. Universal Model Compatibility Tests
# ===========================================================================
def test_universal_tensor_input_compatibility():
    """Verify both BaselineCNN and MobileNetV3 accept identical normalized tensor shape."""
    cnn = BaselineCNN(num_classes=3)
    mobilenet = build_mobilenet_v3(num_classes=3, pretrained=False)

    cnn.eval()
    mobilenet.eval()

    standard_batch = torch.randn(4, 3, 224, 224)

    with torch.no_grad():
        out_cnn = cnn(standard_batch)
        out_mobilenet = mobilenet(standard_batch)

    assert out_cnn.shape == (4, 3)
    assert out_mobilenet.shape == (4, 3)
    assert torch.isfinite(out_cnn).all()
    assert torch.isfinite(out_mobilenet).all()
