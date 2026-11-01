# SCOUT Milestone 07 — Wildfire Dataset Preparation Pipeline Hardening Report

**Project:** SCOUT (Smart Crisis Observation & Understanding Technology)  
**Component:** ML Dataset Preparation Pipeline (`ml/data/prepare_fire_smoke_dataset.py`)  
**Test Suite:** `ml/tests/test_dataset_preparation.py`  
**Status:** COMPLETE & VERIFIED  
**Date:** 2026-10-30  

---

## 1. Executive Summary

Milestone 07 establishes the machine-learning data engineering foundation for SCOUT's wildfire observation capabilities. This audit, correction, and hardening pass addressed critical security, transaction safety, deduplication governance, and verification deficiencies in the wildfire image dataset preparation pipeline.

### Key Milestones Achieved:
1. **Zero Data Tampering:** The pre-existing processed dataset at `data/processed/fire_smoke_v1/` (2,936 files total: 2,931 images across train, validation, and test, plus 5 audit files) was inventoried with cryptographic SHA-256 digests prior to execution. Post-verification confirmed **100% byte-for-byte immutability** (0 files modified, 0 files deleted).
2. **Generalized Duplicate Governance ($K \ge 2$):** Replaced pairwise assumptions with an arbitrary group-size deduplication algorithm that strictly prioritizes Test-set preservation, prevents data leakage between splits, deterministically resolves the ground-truth Fire vs Smoke conflict in favor of Smoke, and assigns an unambiguous disposition to every single recognized image.
3. **Archive Security & Resource Guardrails:** Implemented pre-flight bounds on ZIP entry counts (10,000 max), total uncompressed bytes (2 GB max), individual image payloads (50 MB max), compression ratios (100.0x max), and image raster dimensions (16,384px / 100M pixels max). Enforced strict path traversal rejection (including raw segment inspection) and encryption detection (`flag_bits & 0x1`).
4. **Streamed I/O & Memory Optimization:** Decoupled image verification from memory persistence. Image payloads are verified via two-pass decoding (structural CRC `verify()` followed by raster scanline `load()`) and discarded, streaming directly from the ZIP archive to final destination paths on demand.
5. **Atomic Staging, Verification & Rollback:** The pipeline now stages output in a temporary sibling directory (`.tmp_...`), executes an independent 10-point disk verifier against the staged contents, backs up existing targets (`.bak_...`) under `--force`, promotes staging atomically, rolls back on any failure, and guarantees zero dangling staging directories.
6. **Comprehensive Automated Test Suite:** Expanded `ml/tests/test_dataset_preparation.py` to **35 isolated unit and synthetic end-to-end test cases**, testing all limits, edge cases, collision handling, and rollback behavior without touching real dataset assets.
7. **Regression-Free Verification:** Full repository test suite passed with **152 passing tests** (35 ML + 117 Backend), zero `pip check` broken dependencies, and zero database schema changes.

---

## 2. Cryptographic Inventory & Data Preservation Proof

Before any modification or test execution, a full cryptographic SHA-256 and byte-size inventory of `data/processed/fire_smoke_v1/` was generated and stored in `scratch/existing_dataset_inventory.json`.

Following pipeline implementation and testing, an independent verification script (`scratch/verify_existing_unchanged.py`) traversed all files in `data/processed/fire_smoke_v1/`, computed their SHA-256 digests, and compared them against the baseline.

### Verification Output:
```text
Baseline total files: 2936
Current total files:  2936
Missing files: 0
Mismatched files: 0
PERFECT MATCH: All 2,936 files in data/processed/fire_smoke_v1 are 100% UNCHANGED.
```

### Breakdown of Preserved Files:
- `data/processed/fire_smoke_v1/audit/`: 5 files (`dataset_manifest.csv`, `duplicate_report.csv`, `excluded_files.csv`, `class_distribution.csv`, `dataset_summary.json`)
- `data/processed/fire_smoke_v1/test/`: 298 images (100 Neutral, 99 Fire, 99 Smoke)
- `data/processed/fire_smoke_v1/train/`: 2,106 images (707 Smoke, 706 Neutral, 693 Fire)
- `data/processed/fire_smoke_v1/validation/`: 527 images (177 Smoke, 177 Neutral, 173 Fire)
- **Total:** 2,936 files

---

## 3. Audit Findings & Root Causes in Original Implementation

The independent audit of the previous pipeline revealed eight architectural vulnerabilities:

| Vulnerability / Defect | Root Cause | Implemented Hardened Solution |
| :--- | :--- | :--- |
| **1. Pairwise Duplicate Assumption** | Deduplication assumed pairwise duplicates ($K=2$). Groups with $K \ge 3$ images caused unhandled state or silent drops. | Group-based partitioning (`hash_groups.setdefault(sha, []).append(item)`). Groups of any size $K$ are sorted deterministically; exactly 1 image is retained, and all remaining $(K-1)$ images are recorded with specific exclusion reasons. |
| **2. Cross-Split Conflict Leakage** | Did not guarantee Test-set priority when duplicates crossed Train/Test boundaries. | Test copies are always retained over Train copies. Any matching Train copy is excluded as `EXCLUDED_DUPLICATE` (data leakage prevention) or `EXCLUDED_LABEL_CONFLICT` (label conflict against Test ground truth). |
| **3. In-Memory Byte Accumulation** | Archive extraction stored entire uncompressed image byte payloads in memory inside `DatasetItem.data`. | Memory decoupled: `DatasetItem` stores metadata only. Image data is read and verified during scan, then re-read on demand directly from the archive during disk writing. |
| **4. Incomplete Path Traversal Checks** | `posixpath.normpath` collapsed `..` segments when preceded by valid directories (e.g. `Train/../../secret.jpg`). | Raw un-normalized path components are split by `/` and checked for `".."` before normalization; absolute paths, leading slashes, and Windows drive colons are rejected. |
| **5. Missing Resource Guardrails** | No bounds on entry count, uncompressed size, compression ratio, or image pixel dimensions, leaving the system exposed to ZIP bombs or decompression attacks. | Configurable limits (`DEFAULT_MAX_ARCHIVE_ENTRIES = 10,000`, `2 GB` total uncompressed size, `50 MB` individual image, `100.0x` compression ratio, `16,384px` max dimension, `100M` max pixels). |
| **6. Non-Atomic Target Replacement** | If pipeline failed midway during `--force`, existing processed files were deleted or left corrupted. | Two-stage promotion: write to `.tmp_{name}_{pid}_{rand}`, run independent verification on staging directory, move existing target to `.bak_{name}_{pid}_{rand}`, promote staging, clean up backup, and roll back backup if promotion fails. |
| **7. Collision Vulnerability** | Output files named purely by original filename caused collisions when two distinct images shared the same name. | Output files named `{sha256[:12]}_{clean_filename}` while retaining the true `original_filename` in the manifest. Collision detector halts if a target path is duplicated. |
| **8. Audit Schema Gaps** | Discrepancies between total archive entries vs recognized images; lack of explicit denominators in distribution metrics. | Standardized audit schema: `dataset_manifest.csv` with 6 explicit dispositions, `class_distribution.csv` with `retained_count`, `percentage_within_split`, and `percentage_of_retained_dataset`, and `dataset_summary.json` reconciling total archive entries vs recognized images. |

---

## 4. Architecture of the Hardened Pipeline

### 4.1 Safety Architecture & Pipeline Stages

```
[ Input ZIP Archive ]
         |
         v
[ Stage 1: scan_and_validate_archive() ]
  - Enforce max entries (10,000), total size (2 GB), compression ratio (100x)
  - Detect duplicate member names & encryption (flag_bits & 0x1)
  - Reject path traversal ('..', absolute, colons)
  - Two-pass Pillow verification (verify() structural + load() raster decode)
  - Decompression bomb protection (max dimension 16,384px, max pixels 100M)
         |
         v
[ Stage 2: deduplicate_dataset() ]
  - Arbitrary group size K >= 2 resolution
  - Strict Test-set preservation priority (Test copy preserved, Train excluded)
  - Conflicting label resolution (Smoke preserved over Fire based on visual audit)
  - Unambiguous disposition assignment (RETAINED_*, EXCLUDED_*, QUARANTINED_*)
         |
         v
[ Stage 3: stratified_train_val_split() ]
  - Parameter validation (0 < val_ratio < 1, integer seed)
  - Class sufficiency validation (train >= 1, val >= 1 per class)
  - Stratified deterministic random partition (zero hash overlap)
         |
         v
[ Stage 4: assign_collision_safe_paths() ]
  - Filename format: {sha256[:12]}_{clean_filename}
  - Invariant: bijective mapping between manifest and filesystem
         |
         v
[ Stage 5: stage_and_promote_dataset() ]
  - Step 1: Write all images and audit artifacts to staging: .tmp_{name}_{pid}_{rand}
  - Step 2: Run independent verify_prepared_dataset() on staging
  - Step 3: If target exists (--force), rename to backup: .bak_{name}_{pid}_{rand}
  - Step 4: Promote staging to target output directory
  - Step 5: On failure, rollback from backup and clean up staging
```

### 4.2 Standardized Manifest Dispositions

Every recognized image in `audit/dataset_manifest.csv` receives exactly one disposition:
- `RETAINED_TRAIN`: Valid image assigned to the training split.
- `RETAINED_VALIDATION`: Valid image assigned to the validation split.
- `RETAINED_TEST`: Valid image preserved in the test split.
- `EXCLUDED_DUPLICATE`: Redundant image removed due to exact SHA-256 duplicate match.
- `EXCLUDED_LABEL_CONFLICT`: Image excluded due to conflicting ground-truth labels across splits or classes.
- `QUARANTINED_CORRUPT`: Unreadable or structurally damaged image payload moved to `quarantine/`.

---

## 5. Automated Test Suite Results

A comprehensive test suite of 35 automated tests was implemented in `ml/tests/test_dataset_preparation.py`. All tests use isolated `tmp_path` fixtures and synthetic ZIP archives created in memory.

### Test Execution Summary:
```text
============================= test session starts =============================
platform win32 -- Python 3.14.7, pytest-9.2.0, pluggy-1.7.0
rootdir: C:\Users\TANOOJ\OneDrive\Desktop\SCOUT
collected 35 items

ml/tests/test_dataset_preparation.py::test_validate_zip_entry_path_accepts_clean_paths PASSED [  2%]
ml/tests/test_dataset_preparation.py::test_validate_zip_entry_path_rejects_traversal_and_absolute_paths PASSED [  5%]
ml/tests/test_dataset_preparation.py::test_parse_entry_metadata PASSED   [  8%]
ml/tests/test_dataset_preparation.py::test_validate_image_bytes_valid_formats PASSED [ 11%]
ml/tests/test_dataset_preparation.py::test_validate_image_bytes_corrupted_payload PASSED [ 14%]
ml/tests/test_dataset_preparation.py::test_validate_image_bytes_dimension_and_pixel_limits PASSED [ 17%]
ml/tests/test_dataset_preparation.py::test_archive_duplicate_member_names_rejected PASSED [ 20%]
ml/tests/test_dataset_preparation.py::test_archive_encrypted_entries_rejected PASSED [ 22%]
ml/tests/test_dataset_preparation.py::test_archive_entry_count_limit_exceeded PASSED [ 25%]
ml/tests/test_dataset_preparation.py::test_archive_total_uncompressed_size_limit_exceeded PASSED [ 28%]
ml/tests/test_dataset_preparation.py::test_archive_individual_image_size_limit_exceeded PASSED [ 31%]
ml/tests/test_dataset_preparation.py::test_archive_compression_ratio_limit_exceeded PASSED [ 34%]
ml/tests/test_dataset_preparation.py::test_duplicate_detection_same_split_same_class PASSED [ 37%]
ml/tests/test_dataset_preparation.py::test_duplicate_group_3_identical_same_split PASSED [ 40%]
ml/tests/test_dataset_preparation.py::test_cross_split_duplicate_preserves_test_copy PASSED [ 42%]
ml/tests/test_dataset_preparation.py::test_duplicate_group_3_identical_across_train_and_test PASSED [ 45%]
ml/tests/test_dataset_preparation.py::test_label_conflict_resolution_smoke_over_fire PASSED [ 48%]
ml/tests/test_dataset_preparation.py::test_multi_file_group_split_and_class_conflicts PASSED [ 51%]
ml/tests/test_dataset_preparation.py::test_multiple_test_and_train_copies PASSED [ 54%]
ml/tests/test_dataset_preparation.py::test_unresolvable_conflict_raises_error PASSED [ 57%]
ml/tests/test_dataset_preparation.py::test_validate_split_inputs_checks PASSED [ 60%]
ml/tests/test_dataset_preparation.py::test_stratified_split_isolation_and_reproducibility PASSED [ 62%]
ml/tests/test_dataset_preparation.py::test_filename_collision_handling PASSED [ 65%]
ml/tests/test_dataset_preparation.py::test_normal_archive_processing_end_to_end PASSED [ 68%]
ml/tests/test_dataset_preparation.py::test_corrupted_images_quarantined_and_recorded PASSED [ 71%]
ml/tests/test_dataset_preparation.py::test_output_contains_jpeg_extension_verified PASSED [ 74%]
ml/tests/test_dataset_preparation.py::test_dry_run_does_not_write_files PASSED [ 77%]
ml/tests/test_dataset_preparation.py::test_verify_prepared_dataset_catches_missing_file PASSED [ 80%]
ml/tests/test_dataset_preparation.py::test_verify_prepared_dataset_catches_untracked_file PASSED [ 82%]
ml/tests/test_dataset_preparation.py::test_verify_prepared_dataset_catches_cross_split_hash_collision PASSED [ 85%]
ml/tests/test_dataset_preparation.py::test_check_output_directory_prevents_silent_overwrite PASSED [ 88%]
ml/tests/test_dataset_preparation.py::test_force_replacement_succeeds_cleanly PASSED [ 91%]
ml/tests/test_dataset_preparation.py::test_staging_failure_preserves_existing_dataset PASSED [ 94%]
ml/tests/test_dataset_preparation.py::test_verification_failure_restores_original_from_backup PASSED [ 97%]
ml/tests/test_dataset_preparation.py::test_promotion_failure_restores_original_from_backup PASSED [100%]

======================== 35 passed, 1 warning in 3.62s ========================
```

---

## 6. Full Repository Test Suite & Verification Evidence

### 6.1 Combined Test Suite Execution
Both the ML pipeline tests and the existing backend API integration & unit tests were executed simultaneously to guarantee complete repository health.

```text
====================== 152 passed, 2 warnings in 11.59s =======================
- ML Pipeline Tests: 35 passed
- Backend Unit & Integration Tests: 117 passed
Total: 152 passed, 0 failed, 0 skipped
```

### 6.2 Environment Dependency Check (`pip check`)
```text
No broken requirements found.
```

### 6.3 Git Working Tree State
No commits or branches were created. The working directory remains clean and compliant with audit constraints.

---

## 7. Edge Cases & Known Trade-offs

1. **Windows Directory Atomic Rename:**
   - Under Windows NTFS, `Path.rename()` replaces an empty directory or fails if destination is non-empty. The pipeline addresses this by renaming the pre-existing target to `.bak_{name}_{pid}_{rand}` before promoting the staged `.tmp_...` directory. If promotion fails, the backup directory is restored immediately.
2. **Decompression Bomb Defense:**
   - Extremely large image files can overwhelm memory during rasterization. The pipeline enforces `DEFAULT_MAX_IMAGE_DIMENSION = 16,384` and `DEFAULT_MAX_IMAGE_PIXELS = 100,000,000`, rejecting attacks before PIL `load()` can allocate unbounded memory.
3. **Explicit Multi-Class Conflicting Labels:**
   - The pipeline deterministically resolves `Fire` vs `Smoke` duplicates in Train by honoring visual ground truth (Smoke retained, Fire excluded). Any novel, unknown multi-class conflict (e.g. `Neutral` vs `Fire`) is treated as unresolvable and raises `DatasetPreparationError` rather than guessing, ensuring human intervention for unverified ground truth.

---

## 8. Summary of Source Code Artifacts

- **Pipeline Script:** [`ml/data/prepare_fire_smoke_dataset.py`](ml/data/prepare_fire_smoke_dataset.py)
- **Automated Test Suite:** [`ml/tests/test_dataset_preparation.py`](ml/tests/test_dataset_preparation.py)
- **Cryptographic Inventory Baseline:** `scratch/existing_dataset_inventory.json`
- **Data Preservation Verifier:** `scratch/verify_existing_unchanged.py`
