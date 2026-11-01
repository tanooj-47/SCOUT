# SCOUT Milestone 07 — Phase 7A: Training Pipeline Repair, Checkpoint Integrity & Regression Verification

**Author:** Senior ML Infrastructure Engineer & PyTorch Training Systems Specialist  
**Date:** October 31, 2026  
**Project:** SCOUT — Multimodal Disaster Intelligence & Response Platform  
**Target:** Training Engine Early Stopping Logic, Checkpoint Selection Safety & Regression Verification  
**Milestone Status:** **`COMPLETE`**  

---

## 1. Executive Summary

Milestone 07 Phase 7A was initiated following the discoveries of the Phase 6 audit, which established that the historical best checkpoint for `BaselineCNN` stored in `artifacts/checkpoints/baseline_cnn_best.pt` was inadvertently overwritten on every epoch through early stopping termination at Epoch 21, rather than preserving the genuine peak performance weights from Epoch 15.

The primary objective of Phase 7A was to inspect the entire training system, repair the early-stopping return-value handling at all call sites, add defense-in-depth type guards to [`Trainer.save_epoch_checkpoint`](../../ml/training/engine.py), implement rigorous regression tests covering tuple semantics, min-delta behavior, patience exhaustion, and stage-specific transitions, and guarantee that all existing historical checkpoints and dataset files remain bitwise preserved.

### Core Achievements

1. **Root Cause Resolved:** The tuple-truthiness defect where Python evaluates `bool((False, False))` as `True` was resolved across all callers and reinforced at the engine level.
2. **Defensive Guards Implemented:**
   - [`EarlyStoppingResult`](../../ml/training/early_stopping.py): A dedicated `NamedTuple` subclassing `Tuple[bool, bool]` that makes returned signals explicit (`res.improved`, `res.should_stop`) while preserving seamless tuple unpacking (`improved, should_stop = es.update(...)`).
   - [`Trainer.save_epoch_checkpoint`](../../ml/training/engine.py): Implemented a strict runtime typecheck raising `TypeError` if `is_best` is passed an un-unpacked tuple or non-boolean, preventing silent checkpoint overwrites.
   - [`EarlyStopping.update`](../../ml/training/early_stopping.py): Implemented finite-number checks rejecting `NaN`, `+Inf`, and `-Inf` with a descriptive `ValueError`.
   - Added [`Trainer.step_early_stopping`](../../ml/training/engine.py) to encapsulate early stopping updates cleanly.
3. **Automated Regression Suite:** Created [`ml/tests/test_training_integrity.py`](../../ml/tests/test_training_integrity.py) with 9 comprehensive tests covering all required scenarios (C1 through C6). All 9 tests passed.
4. **Zero Checkpoint Mutation:** Cryptographic SHA-256 verification confirmed that all 6 historical Phase 5 checkpoints in `artifacts/checkpoints/` remain **100% byte-identical** before and after changes.
5. **Zero Dataset Mutation:** All 2,936 historical dataset files in `data/processed/fire_smoke_v1/` remain **100% byte-identical**.
6. **Full Test Suite Pass:** The complete ML test suite expanded to **126 tests** (all passing), 74 backend non-database tests passed, 5 Alembic unit tests passed, and dependency integrity is clean.

---

## 2. Root Cause of the Checkpoint Overwrite Bug

### 2.1 Bug Mechanism

In Python, the boolean value of any non-empty tuple evaluates to `True`, regardless of its elements:

```python
bool((False, False)) is True
bool((False, True)) is True
```

In [`ml/training/early_stopping.py`](../../ml/training/early_stopping.py), the `EarlyStopping.update()` method was designed to return a 2-tuple indicating both improvement and stopping status:

```python
return improved, self.should_stop
```

However, in `scratch/run_full_training_and_evaluation.py`, the training loops handled the return value as follows:

```python
# Previous flawed code
is_improved = trainer.early_stopping.update(val_metrics["macro_f1"])
if is_improved:
    best_val_macro_f1 = val_metrics["macro_f1"]
    best_epoch = epoch

trainer.save_epoch_checkpoint(val_metrics, is_best=is_improved)
```

Because `is_improved` was assigned the tuple `(improved, should_stop)`:
1. `if is_improved:` evaluated to `True` on **every single epoch**.
2. `best_epoch` was set to the current epoch on **every single epoch**.
3. `is_best=is_improved` passed the tuple to `Trainer.save_epoch_checkpoint()`.
4. Inside `save_epoch_checkpoint()`, `if is_best:` evaluated to `True` on **every single epoch**.
5. As a consequence, `artifacts/checkpoints/baseline_cnn_best.pt` was continuously overwritten on all 21 epochs.

### 2.2 Historical Status of Phase 5 Weights

- **Epoch 15 Weights:** The Phase 5 training history records that validation Macro F1 peaked at **0.8858** at Epoch 15. However, due to the continuous overwriting bug, Epoch 15 weights were overwritten on Epochs 16, 17, 18, 19, 20, and 21.
- **Actual Saved Checkpoint:** Direct inspection of `artifacts/checkpoints/baseline_cnn_best.pt` confirmed `checkpoint["global_epoch"] == 21` and `checkpoint["current_metrics"]["macro_f1"] == 0.8808`.
- **Engineering Reality:** The original Epoch 15 weights are permanently unavailable because no independent backup copy exists. In accordance with strict engineering ethics, SCOUT does not fabricate or simulate missing historical weights. The checkpoint is documented truthfully as containing Epoch 21 weights.

---

## 3. Comprehensive Call Site Inventory

An AST-based repository search inspected every occurrence of `EarlyStopping`, `.update(`, and checkpoint-saving routines:

| File Path | Line | Context | Return Handling | Flaw Present? | Severity | Action Taken |
| :--- | :---: | :--- | :--- | :---: | :---: | :--- |
| `scratch/run_full_training_and_evaluation.py` | 165 | BaselineCNN epoch loop | Assigned tuple to `is_improved`; checked `if is_improved:` | **YES** | **CRITICAL** | Corrected to unpack `improved, should_stop = ...` |
| `scratch/run_full_training_and_evaluation.py` | 354 | MobileNetV3 Stage 2 loop | Assigned tuple to `is_improved`; checked `if is_improved:` | **YES** | **CRITICAL** | Corrected to unpack `improved, should_stop = ...` |
| `scratch/run_full_training_and_evaluation.py` | 278 | MobileNetV3 Stage 1 loop | Direct comparison `val_f1 > best_f1` (bool) | **NO** | None | Verified clean; early stopping is not applied in Stage 1 warmup. |
| [`ml/tests/test_training.py`](../../ml/tests/test_training.py) | 256 | `test_early_stopping_patience_and_delta` | Properly unpacked `improved, stop = es.update(...)` | **NO** | None | Verified clean. |
| [`ml/tests/test_training.py`](../../ml/tests/test_training.py) | 290 | `test_early_stopping_reset_on_significant_improvement` | Properly unpacked `improved, stop = es.update(...)` | **NO** | None | Verified clean. |
| [`ml/training/engine.py`](../../ml/training/engine.py) | 380 | `Trainer.save_epoch_checkpoint` | `is_best: bool = False`; checked `if is_best:` | **DEFENSE GAP** | **HIGH** | Added strict runtime check: `if not isinstance(is_best, bool): raise TypeError(...)` |

Serialized to `artifacts/audits/m07_phase7a/training_callsite_audit.json`.

---

## 4. Implementation Corrections & Defensive Architecture

### 4.1 `EarlyStoppingResult` NamedTuple

In [`ml/training/early_stopping.py`](../../ml/training/early_stopping.py):

```python
class EarlyStoppingResult(NamedTuple):
    improved: bool
    should_stop: bool
```

`EarlyStopping.update()` now returns `EarlyStoppingResult(improved=improved, should_stop=self.should_stop)`. This yields three critical engineering advantages:
1. **Full Backwards Compatibility:** Because it inherits from `tuple`, standard tuple unpacking `improved, should_stop = es.update(...)` works identically.
2. **Explicit Attribute Access:** Callers can access `res.improved` and `res.should_stop` without relying on magic tuple indexing.
3. **Rejection of Non-Finite Scores:** Added input validation rejecting `NaN`, `+Inf`, and `-Inf` with `ValueError`, ensuring metric calculation divergence fails fast.

### 4.2 Runtime Type Guard in `Trainer.save_epoch_checkpoint`

In [`ml/training/engine.py`](../../ml/training/engine.py):

```python
def save_epoch_checkpoint(
    self,
    val_metrics: Dict[str, Any],
    is_best: bool = False,
) -> Tuple[Path, Optional[Path]]:
    if not isinstance(is_best, bool):
        raise TypeError(
            f"is_best must be a strict boolean (True or False), got {type(is_best).__name__}: {is_best!r}. "
            "Ensure EarlyStopping.update() return values are unpacked into (improved, should_stop) "
            "before passing is_best."
        )
```

This defense-in-depth guard ensures that even if a future caller accidentally passes an unpacked tuple or non-boolean, Python immediately halts with a descriptive `TypeError` rather than corrupting checkpoint storage.

### 4.3 Safe Runner Integration

In `scratch/run_full_training_and_evaluation.py`:

```python
# Both BaselineCNN (Line 165) and MobileNetV3 Stage 2 (Line 354)
improved, should_stop = trainer.early_stopping.update(val_metrics["macro_f1"])
if improved:
    best_val_macro_f1 = val_metrics["macro_f1"]
    best_epoch = epoch

# Atomically saves last checkpoint; saves best checkpoint ONLY if improved is True
trainer.save_epoch_checkpoint(val_metrics, is_best=improved)

if should_stop:
    print(f"Early stopping triggered at epoch {epoch} (patience={config.baseline_patience}).")
    early_stopped = True
    break
```

---

## 5. Automated Regression Test Suite

Created a dedicated test module [`ml/tests/test_training_integrity.py`](../../ml/tests/test_training_integrity.py) containing 9 targeted unit tests:

| Test Name | Category | Scope & Invariants Verified | Result |
| :--- | :---: | :--- | :---: |
| `test_early_stopping_result_named_tuple_unpacking` | **C1** | Verifies `EarlyStoppingResult` unpacks as `(improved, should_stop)` and supports named attribute access. | **PASSED** |
| `test_tuple_semantics_gating_behavior` | **C1** | Verifies `(False, False)` saves last only, `(True, False)` saves best+last, `(False, True)` saves last+stop, and `(True, True)` saves best+stop. | **PASSED** |
| `test_save_epoch_checkpoint_rejects_non_boolean_is_best` | **C1** | Verifies `save_epoch_checkpoint` strictly raises `TypeError` if passed `(False, False)`, `(True, False)`, or an int. | **PASSED** |
| `test_best_checkpoint_integrity_on_metric_sequence` | **C2** | Simulates `[0.70, 0.75, 0.73, 0.74, 0.80, 0.78]`; confirms best checkpoint strictly holds Epoch 5 (0.80) and non-improving epochs do not overwrite it. | **PASSED** |
| `test_min_delta_strict_enforcement` | **C3** | Verifies scores $< \text{best} + \text{min\_delta}$ increment patience, while $\ge \text{best} + \text{min\_delta}$ reset patience. | **PASSED** |
| `test_early_stopping_rejects_non_finite_scores` | **C3** | Verifies `EarlyStopping.update` rejects `NaN`, `+Inf`, and `-Inf` with `ValueError`. | **PASSED** |
| `test_early_stopping_exhaustion_and_best_checkpoint_preservation` | **C4** | Verifies training halts exactly at patience=3 and best checkpoint from Epoch 1 remains completely intact. | **PASSED** |
| `test_early_stopping_serialization_and_restoration_parity` | **C5** | Verifies `state_dict()` and `load_state_dict()` preserve best score and patience counter across training resumption. | **PASSED** |
| `test_stage_specific_checkpoints_and_optimizer_isolation` | **C6** | Verifies Stage 1 and Stage 2 maintain separate checkpoint filenames, optimizer is discarded and rebuilt, and stage transition loads best Stage 1 weights. | **PASSED** |

Serialized to `artifacts/audits/m07_phase7a/early_stopping_test_results.json`.

---

## 6. Checkpoint Safety & Historical Artifact Preservation

Before applying any source code modifications, SHA-256 cryptographic hashes and byte sizes were recorded for all 6 existing Phase 5 checkpoints in `artifacts/checkpoints/`. Following implementation and test execution, all checkpoints were re-hashed and compared:

| Checkpoint File | Size (Bytes) | SHA-256 Hash | Integrity Status |
| :--- | :---: | :--- | :---: |
| `baseline_cnn_best.pt` | 4,916,877 | `76544190318f1300b2b48e8ede5062b8fa712368e246d52611bdf4adb035150e` | **MATCH (100% Identical)** |
| `baseline_cnn_last.pt` | 4,916,877 | `eb5725ebc72466d778cd239fde4ed6dca382b9799d3c05e5df8d5135221202b4` | **MATCH (100% Identical)** |
| `mobilenet_v3_small_stage1_best.pt` | 10,998,699 | `8f7878c47512266719b203958bba94612b44af5ccfe67c7223bace2952ad9d3a` | **MATCH (100% Identical)** |
| `mobilenet_v3_small_stage1_last.pt` | 10,998,699 | `86d0a7dbae585c32ed1e99871b3b3dc15712adb156793d2ef531aecaec929ba5` | **MATCH (100% Identical)** |
| `mobilenet_v3_small_stage2_best.pt` | 16,928,947 | `278250a69570e2bf024e48e87e345b6d4a75cf25ec4d0e887194a8e5063fccd1` | **MATCH (100% Identical)** |
| `mobilenet_v3_small_stage2_last.pt` | 16,928,947 | `c6b3aecba0713596a68d268259978b539efc5a58f11415f228b325cdf99469fb` | **MATCH (100% Identical)** |

Serialized to `artifacts/audits/m07_phase7a/checkpoint_hashes_before.json`, `artifacts/audits/m07_phase7a/checkpoint_hashes_after.json`, and `artifacts/audits/m07_phase7a/checkpoint_integrity_verification.json`.

---

## 7. Full Regression Verification Results

| Suite / Verification Check | Scope | Passed | Failed | Status |
| :--- | :--- | :---: | :---: | :---: |
| **New Training Integrity Suite** | `pytest ml/tests/test_training_integrity.py` | 9 | 0 | **PASSED** (10.11s) |
| **Complete ML Test Suite** | `pytest ml/tests/ -v` | 126 | 0 | **PASSED** (62.75s) |
| **Backend Non-Database Suite** | `pytest backend -m "not database" -c backend/pytest.ini` | 74 | 0 | **PASSED** (3.72s) |
| **Alembic Unit Tests** | `pytest backend/tests/unit/test_alembic*` | 5 | 0 | **PASSED** (4.33s) |
| **Dependency Integrity** | `python -m pip check` | — | — | **CLEAN** ("No broken requirements found.") |
| **Dataset SHA-256 Inventory** | `python scratch/verify_existing_unchanged.py` | 2,936 | 0 | **100% MATCH** (Zero file modifications) |
| **Git Working Tree** | `git status` | — | — | **NO COMMITS / UNSTAGED** |

---

## 8. Explicit Compliance Statements

1. **Old Phase 5 Best Checkpoint Overwrite:** Confirmed. `artifacts/checkpoints/baseline_cnn_best.pt` holds Epoch 21 weights (`val_macro_f1 = 0.8808`), having been overwritten at every epoch due to the tuple-truthiness bug.
2. **Missing Epoch 15 Weights:** The genuine Epoch 15 peak weights were not recovered and are considered permanently unavailable because no uncorrupted backup exists. No weights were fabricated or simulated.
3. **No Model Retraining:** Exactly **zero (0) models** were retrained during Phase 7A.
4. **No Dataset Modification:** The processed dataset `data/processed/fire_smoke_v1/` remains strictly untouched.
5. **No Git Commits:** Exactly **zero (0) commits or pushes** were performed.
6. **Report Preservation:** Historical reports for Milestone 05, 06, Phase 5, and Phase 6 remain completely unmodified.

---

## 9. Remaining Limitations & Next Steps

1. **Historical Checkpoint Parity Gap:** The current Phase 5 baseline model weights represent Epoch 21, not the ideal validation peak at Epoch 15.
2. **Future Clean Retraining:** When dataset balance remediation is implemented in Phase 7B (adding diverse low-resolution JPEG neutral scenes and high-resolution TIFF disaster captures), full retraining will naturally produce clean, uncorrupted best checkpoints under the repaired training engine.
3. **Next Recommended Step:** Proceed to Milestone 07 Phase 7B (Dataset Hardening and Multi-Source Balance).
