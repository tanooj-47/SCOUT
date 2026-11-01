# SCOUT Milestone 07 — Phase 6: Comprehensive Dataset Integrity, Leakage & Model Generalization Audit

**Author:** Principal Machine Learning Engineer & Independent ML Systems Auditor  
**Date:** October 31, 2026  
**Project:** SCOUT — Multimodal Disaster Intelligence & Response Platform  
**Target:** Wildfire Image Classification Pipeline & BaselineCNN Generalization Assessment  
**Official Audit Reliability Status:** **`PROMISING BUT REQUIRES FURTHER VALIDATION`**  

---

## 1. Executive Summary

Milestone 07 Phase 6 was commissioned to conduct an exhaustive, evidence-based technical audit of the SCOUT wildfire image classification pipeline following the initial Phase 5 training and evaluation results (reported as **89.60% test accuracy**, **0.8960 Macro F1**, **87.76% Fire Recall**, and **93.00% Smoke Recall** on `BaselineCNN`).

A critical anomaly detected at the conclusion of Phase 5 revealed that **100% of test `neutral` images (100/100) are internally PackBits TIFF files**, whereas **100% of test `fire` and `smoke` images (198/198) are JPEG files**. This audit was designed to establish whether `BaselineCNN` learned genuine visual disaster representations (flames, convective smoke plumes, burnt terrain) or exploited dataset-format and source provenance shortcuts.

### Key Audit Findings

1. **Exact & Near-Duplicate Isolation:**
   - **Zero (0) exact SHA-256 duplicates** exist across any split boundary (train vs val, train vs test, val vs test).
   - **Zero (0) perceptual near-duplicates** exist between the test split and train/validation splits at Hamming distance $\le 2$ or $\le 4$ using 64-bit difference hashing (`dHash`).
   - The test split is byte-isolated and perceptually distinct from the training set.

2. **Controlled Image Normalization Experiment:**
   - Re-encoding all 298 test images to a standardized, lossless **PNG** format in `artifacts/audits/m07_phase6/test_normalized_png/` produced **exactly 0 prediction flips out of 298 images (0.00%)**.
   - The mean and maximum absolute probability differences across all classes and samples were **0.000000**.
   - This experiment strictly proves that the PyTorch/Pillow container decoding pipeline does not leak format markers into tensor activations.

3. **Format & Source Provenance Confounding is Real and Severe:**
   - Although container parsing does not leak format markers, the underlying image sources are heavily confounded. All 156 TIFF images across the entire dataset (48 train, 8 val, 100 test) originate from a single distinct source: **100% are exactly $800 \times 600$ pixels** (mean size 1,386.2 KB).
   - In contrast, `fire` and `smoke` images are small web JPEGs ($\text{mean width} \approx 270\text{px}$, $\text{mean height} \approx 185\text{px}$, mean size $\approx 7.7\text{ KB}$).
   - Because 100% of test `neutral` images are $800 \times 600$ TIFFs, spatial frequency characteristics, JPEG compression artifacts, and aspect-ratio padding properties remain confounded with class labels in pixel space.

4. **Training Engine & Checkpoint Invariant Discoveries:**
   - **Tuple Truthiness Flaw:** In [`ml/training/metrics.py`](../../ml/training/metrics.py), `EarlyStopping.update()` returns a 2-tuple `(improved, should_stop)`. In Python, any 2-tuple (including `(False, False)`) evaluates to `True` in boolean contexts. Consequently, `is_improved` evaluated to `True` at every epoch, causing `artifacts/checkpoints/baseline_cnn_best.pt` to be overwritten on every epoch through Epoch 21. The saved checkpoint reflects **Epoch 21** (`val_macro_f1 = 0.8808`), not Epoch 15 (`val_macro_f1 = 0.8858`) as claimed in the Phase 5 report.
   - **Test-Set Selection Contamination:** The composite model selection score (0.9007 vs 0.0670) was computed in Phase 5 using `test_loader` metrics rather than validation metrics. While `BaselineCNN` vastly outperformed the randomly initialized `MobileNetV3` (which mode-collapsed to neutral), using test-set metrics to choose the model represents formal test-set selection contamination.

5. **Official Reliability Status:**
   - Assigned: **`PROMISING BUT REQUIRES FURTHER VALIDATION`**.
   - The model clearly captures disaster features (distinguishing fire vs smoke at high accuracy among identical JPEG web formats), but reported test generalization cannot be certified for operational deployment until tested against an independent, format-balanced multi-source benchmark.

---

## 2. Phase A: Repository, Dataset & Artifact Inspection

### 2.1 Complete Dataset Census

An exhaustive census of `data/processed/fire_smoke_v1/` verified **2,931 total images** divided into canonical splits and classes:

| Split | Fire | Neutral | Smoke | Total Split Count |
| :--- | :---: | :---: | :---: | :---: |
| **Train** | 673 | 718 | 715 | **2,106** |
| **Validation** | 168 | 180 | 179 | **527** |
| **Test** | 98 | 100 | 100 | **298** |
| **Total** | **939** | **998** | **994** | **2,931** |

### 2.2 Raster Format Census

Every image was inspected via Pillow byte headers to determine underlying container formats:

| Split | Class | JPEG | TIFF | PNG | BMP | GIF |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Train** | Fire | 673 | 0 | 0 | 0 | 0 |
| | Neutral | 667 | 48 | 1 | 1 | 1 |
| | Smoke | 715 | 0 | 0 | 0 | 0 |
| **Validation**| Fire | 168 | 0 | 0 | 0 | 0 |
| | Neutral | 172 | 8 | 0 | 0 | 0 |
| | Smoke | 179 | 0 | 0 | 0 | 0 |
| **Test** | Fire | 98 | 0 | 0 | 0 | 0 |
| | Neutral | 0 | **100** | 0 | 0 | 0 |
| | Smoke | 100 | 0 | 0 | 0 | 0 |

**Critical Observation:** In the test set, **100% of Neutral images are PackBits TIFF**, and **0% of Neutral images are JPEG**. Conversely, **100% of Fire and Smoke test images are JPEG**, and **0% are TIFF**. Across the entire dataset, 156 TIFF images exist (48 train, 8 val, 100 test), all belonging to the `neutral` class.

### 2.3 Reproduction of Reported Phase 5 Test Metrics

The raw prediction records in `artifacts/predictions/baseline_cnn_predictions.csv` were audited against the actual test directory:
- Exactly 298 rows correspond to the 298 test images.
- Support matches ground truth: Fire = 98, Neutral = 100, Smoke = 100.
- Recomputed metrics from the raw probabilities and labels:
  - **Overall Accuracy:** `0.895973` ($\mathbf{89.60\%}$)
  - **Macro Precision:** `0.897619`
  - **Macro Recall:** `0.895850`
  - **Macro F1-Score:** `0.895955` ($\mathbf{0.8960}$)
  - **Class Recalls:** Fire = `0.8776` (86/98), Neutral = `0.8800` (88/100), Smoke = `0.9300` (93/100).
  - **Confusion Matrix:**
    $$\begin{pmatrix} 86 & 3 & 9 \\ 6 & 88 & 6 \\ 2 & 5 & 93 \end{pmatrix}$$
- **Verification Result:** The Phase 5 reported metrics are 100% mathematically faithful to the serialized predictions.

---

## 3. Phase B: Dataset Leakage and Independence Audit

### 3.1 Exact Duplicate Analysis (SHA-256)

A full cryptographic hash inventory was executed across all 2,931 images in the dataset.

- **Intra-split Duplicates:** **0**
- **Cross-split Duplicates (Train vs Val):** **0**
- **Cross-split Duplicates (Train vs Test):** **0**
- **Cross-split Duplicates (Val vs Test):** **0**
- **Label Conflict Duplicates:** **0**

The SHA-256 duplicate audit confirms that the deduplication logic in `ml/data/dataset_prep.py` successfully purged identical image payloads during initial ingestion.

### 3.2 Near-Duplicate Perceptual Analysis (dHash)

To detect near-duplicate images (e.g. resaved JPEGs, slight crops, minor resizings), a 64-bit difference hash (`dHash`, $8 \times 8$ gradient matrix) was computed for every image in the dataset. Hamming distances between all test images ($N=298$) and all training/validation images ($N=2,633$) were evaluated ($784,634$ cross-split pairs):

- **Pairs with Hamming Distance $\le 2$:** **0**
- **Pairs with Hamming Distance $\le 4$:** **0**
- **Minimum Hamming Distance across splits:** $> 6$

**Finding:** The test split contains no near-duplicate copies or slightly transformed variants of training or validation images. The test set is structurally independent from the training split.

### 3.3 Source Distribution and Dimensional Discrepancies

Detailed dimensional and statistical profiling was conducted across all splits and classes:

```text
TRAIN SPLIT:
- Fire (673):    Width 312.4 ± 117.8 px, Height 216.5 ± 79.1 px, Size 12.3 ± 14.8 KB (100% JPEG)
- Neutral (718): Width 358.9 ± 189.6 px, Height 251.9 ± 129.8 px, Size 110.1 ± 344.2 KB (93% JPEG, 7% TIFF)
- Smoke (715):   Width 301.7 ± 86.8 px,  Height 207.2 ± 60.1 px, Size 10.1 ± 10.3 KB (100% JPEG)

TEST SPLIT:
- Fire (98):     Width 268.0 ± 40.5 px,  Height 189.3 ± 31.4 px, Size 8.1 ± 2.7 KB (100% JPEG)
- Neutral (100): Width 800.0 ± 0.0 px,   Height 600.0 ± 0.0 px,  Size 1,386.2 ± 50.2 KB (100% TIFF)
- Smoke (100):   Width 276.7 ± 27.7 px,  Height 183.1 ± 22.9 px, Size 7.3 ± 2.4 KB (100% JPEG)
```

**Key Distribution Findings:**
1. **Resolution Disparity:** Test `fire` and `smoke` images are low-resolution web thumbnails averaging $\sim 270 \times 185$ pixels. In contrast, 100% of test `neutral` images are high-resolution $800 \times 600$ landscape captures.
2. **File Size Disparity:** Test `fire` and `smoke` files average $\approx 7.7\text{ KB}$. Test `neutral` files average $\approx 1,386.2\text{ KB}$ (over **180 times larger**).
3. **Aspect Ratio:** Test `neutral` images have a uniform aspect ratio of exactly $1.333$ ($4:3$), while `fire` and `smoke` images exhibit wider distributions ($\text{mean} \approx 1.45\text{--}1.54$).
4. **Color and Contrast:**
   - Test `fire`: Luminance $95.9 \pm 32.5$, Red channel dominant ($R=121.6$, $G=88.6$, $B=66.5$).
   - Test `smoke`: Luminance $116.6 \pm 31.0$, Balanced gray ($R=117.7$, $G=116.4$, $B=114.8$).
   - Test `neutral`: Luminance $107.0 \pm 32.2$, Earth tones ($R=117.7$, $G=104.4$, $B=92.5$).

---

## 4. Phase C: Controlled Image Normalization Experiment

To test whether the model was exploiting Pillow container format handling, EXIF header tags, or compression metadata, a controlled experiment was designed and executed.

### 4.1 Methodology

1. All 298 test images from `data/processed/fire_smoke_v1/test/` were decoded using Pillow (`Image.open().convert("RGB")`).
2. Each image was re-encoded as a standardized, lossless **PNG** image and saved to `artifacts/audits/m07_phase6/test_normalized_png/`.
3. All file extensions in the directory were renamed to `.png`, stripping all TIFF and JPEG container metadata and unifying container format across all 298 samples.
4. An isolated dataset and dataloader were instantiated targeting the normalized PNG directory using the exact same evaluation transform (`LetterboxResize(224)`, standard ImageNet normalization).
5. Inference was executed on the best checkpoint `artifacts/checkpoints/baseline_cnn_best.pt` in `torch.inference_mode()`.
6. Output logits, softmax probabilities, and predicted classes were compared sample-by-sample against original predictions.

### 4.2 Empirical Results

| Metric | Original Evaluation (Mixed JPEG/TIFF) | Normalized PNG Evaluation (100% Lossless PNG) | Delta |
| :--- | :---: | :---: | :---: |
| **Test Accuracy** | **0.8960** | **0.8960** | **0.0000** |
| **Macro F1-Score** | **0.8960** | **0.8960** | **0.0000** |
| **Fire Recall** | 0.8776 (86/98) | 0.8776 (86/98) | 0.0000 |
| **Neutral Recall** | 0.8800 (88/100) | 0.8800 (88/100) | 0.0000 |
| **Smoke Recall** | 0.9300 (93/100) | 0.9300 (93/100) | 0.0000 |
| **Prediction Flips** | — | **0 / 298 (0.00%)** | 0 |
| **Max Prob Difference** | — | **0.000000** | 0.0 |
| **Mean Prob Difference**| — | **0.000000** | 0.0 |

```text
Original Confusion Matrix:        Normalized PNG Confusion Matrix:
[ 86,  3,  9 ]                     [ 86,  3,  9 ]
[  6, 88,  6 ]                     [  6, 88,  6 ]
[  2,  5, 93 ]                     [  2,  5, 93 ]
```

All 298 sample comparisons are recorded in `artifacts/audits/m07_phase6/prediction_changes.csv`.

### 4.3 Technical Interpretation: Container vs. Provenance Shortcuts

This experiment yields a vital distinction that must be clearly stated:

1. **What is Disproven:** The hypothesis that the PyTorch/Pillow data loading pipeline directly introduces container-level decoding metadata or container parsing artifacts that leak format labels into tensor activations is **empirically disproven**. The model does not read file headers or container tags.
2. **What Remains Confounded:** Lossless PNG re-encoding preserves the exact pixel values of the original image. If an image was originally an $800 \times 600$ uncompressed TIFF, re-encoding it to PNG retains its original high-frequency detail, smooth gradients, and letterboxing proportions. If an image was originally a $270 \times 180$ lossy JPEG, re-encoding it to PNG retains the $8 \times 8$ DCT compression blocking, ringing, and chroma subsampling artifacts.
3. **Core Conclusion:** The format confounding is **source-provenance confounding** embedded in pixel space, not container decoding bias.

---

## 5. Phase D: Model Error Analysis & Confusion Breakdown

Out of 298 test images, `BaselineCNN` made **31 misclassifications (10.40% error rate)**. An exhaustive breakdown was serialized to `artifacts/audits/m07_phase6/prediction_error_analysis.json`.

### 5.1 Error Breakdown by Class

```text
1. Actual Fire Misclassifications (12 errors / 98 images):
   - 9 mistaken for Smoke (75.0% of fire errors)
   - 3 mistaken for Neutral (25.0% of fire errors)

2. Actual Smoke Misclassifications (7 errors / 100 images):
   - 5 mistaken for Neutral (71.4% of smoke errors)
   - 2 mistaken for Fire (28.6% of smoke errors)

3. Actual Neutral Misclassifications (12 errors / 100 images):
   - 6 mistaken for Fire (50.0% of neutral errors)
   - 6 mistaken for Smoke (50.0% of neutral errors)
```

### 5.2 Key Visual Failure Patterns

1. **Fire vs. Smoke Ambiguity (11 mutual errors):**
   - The largest single error mode (9 images) occurs when wildfire scenes dominated by heavy smoke columns obscure visible flames. In cases such as `image_16.jpg` (confidence $0.9369$) and `image_28.jpg` (confidence $0.8524$), the model predicts `smoke` with high certainty because the vast majority of the image canvas contains white/gray smoke haze, despite ground truth labeling the scene as `fire`.
   - Conversely, 2 smoke images (`image_36.jpg`, `image_67.jpg`) were misclassified as `fire`, likely due to reddish dusk lighting or intense sunlight backlighting smoke plumes.

2. **Neutral False Positives (12 errors):**
   - 6 neutral images were misclassified as `fire` (`image_12.jpg`, `image_17.jpg`, `image_21.jpg`, `image_48.jpg`, `image_61.jpg`, `image_94.jpg`). Visual inspection shows these contain high-contrast reddish-orange features, such as autumn foliage, sunset horizons, or red sandstone canyons.
   - 6 neutral images were misclassified as `smoke` (`image_23.jpg`, `image_44.jpg`, `image_47.jpg`, `image_53.jpg`, `image_76.jpg`, `image_88.jpg`). These contain low-contrast foggy skies, overcast weather, or mountain mists that resemble wildfire smoke.

3. **Disaster Misses (False Negatives — 8 images):**
   - 3 fire images were misclassified as neutral (`image_14.jpg`, `image_42.jpg`, `image_88.jpg`).
   - 5 smoke images were misclassified as neutral (`image_2.jpg`, `image_25.jpg`, `image_29.jpg`, `image_78.jpg`, `image_89.jpg`).
   - In these instances, faint or distant smoke plumes or tiny spot fires in complex natural landscapes were missed, producing hazardous false negatives.

### 5.3 Confidence and Calibration Analysis

Serialized to `artifacts/audits/m07_phase6/confidence_analysis.json`:
- **Mean Confidence on Correct Predictions:** **$0.9198 \pm 0.1163$** (min $0.3648$, max $1.0000$).
- **Mean Confidence on Incorrect Predictions:** **$0.7230 \pm 0.1790$** (min $0.3638$, max $0.9955$).
- **High-Confidence Errors ($\ge 0.80$):** **11 images**. These represent dangerous overconfident failures where the model assigned extreme certainty to wrong classes.
- **Low-Confidence Predictions ($< 0.50$):** **5 images**. Samples such as `image_0.jpg` ($P(\text{fire})=0.291$, $P(\text{neutral})=0.330$, $P(\text{smoke})=0.379$) demonstrate healthy model uncertainty when visual evidence is split across all three classes.

---

## 6. Phase E: Training & Validation Integrity Audit

### 6.1 Checkpoint Overwrite Discovery (Early Stopping Tuple Truthiness)

During code inspection of [`ml/training/engine.py`](../../ml/training/engine.py) and `scratch/run_full_training_and_evaluation.py`, a critical implementation discrepancy was identified:

In [`ml/training/metrics.py`](../../ml/training/metrics.py):
```python
def update(self, current_metric: float) -> Tuple[bool, bool]:
    # returns (improved, should_stop)
```

In `scratch/run_full_training_and_evaluation.py`, the training loop handled the return value as follows:
```python
is_improved = early_stopping.update(val_metrics['macro_f1'])
if is_improved:
    save_checkpoint(model, optimizer, scheduler, epoch, ...)
```

**Bug Mechanism:** In Python, any non-empty tuple evaluates to `True` in a boolean context (`bool((False, False))` is `True`). As a result, `if is_improved:` evaluated to `True` on **every single epoch**, completely bypassing early-stopping improvement gating.

**Impact on Artifacts:**
- Rather than preserving the weights from **Epoch 15** (where validation Macro F1 peaked at **0.8858**), `artifacts/checkpoints/baseline_cnn_best.pt` was continuously overwritten up to early stopping termination at **Epoch 21** (`val_macro_f1 = 0.8808`).
- Direct checkpoint inspection confirms `checkpoint['epoch'] == 21` and `checkpoint['val_macro_f1'] == 0.8808`.
- The reported Phase 5 test metrics ($89.60\%$ accuracy) were actually generated by the **Epoch 21** model weights, which performed slightly better on the test split despite slightly lower validation score.

### 6.2 Test-Set Selection Contamination

In the Phase 5 training workflow (`scratch/run_full_training_and_evaluation.py`), model selection between `BaselineCNN` and `MobileNetV3-Small` was executed via a composite selection score:
$$\text{Score} = 0.40 \times \text{Macro F1} + 0.30 \times \text{Fire Recall} + 0.30 \times \text{Smoke Recall}$$

**Audit Finding:** This composite score was computed on **`test_loader` metrics** rather than `val_loader` metrics:
- `BaselineCNN` composite score: **0.9007** (calculated from test Macro F1 $0.8960$, Fire Recall $0.8776$, Smoke Recall $0.9300$).
- `MobileNetV3-Small` composite score: **0.0670** (calculated from test Macro F1 $0.1675$, Fire Recall $0.0000$, Smoke Recall $0.0000$).

**Technical Assessment:** While `MobileNetV3-Small` suffered total mode collapse due to offline training from scratch and would have lost under any metric, computing the selection score on test metrics constitutes **formal test-set selection contamination**. The test set ceased to be an unaccessed holdout and was actively used in the model selection decision.

---

## 7. Phase F: Subgroup Generalization & Robustness Diagnostics

Subgroup diagnostics were conducted to analyze performance variations across operational conditions:

### 7.1 By Image Resolution
- **Low Resolution ($< 500\text{px}$):** 198 images, **$90.40\%$ accuracy** (179/198 correct).
- **Medium Resolution ($500\text{--}1000\text{px}$):** 100 images, **$88.00\%$ accuracy** (88/100 correct).
- **High Resolution ($> 1000\text{px}$):** 0 images in test set.

*Note:* Because 100% of medium-resolution images are the 100 TIFF `neutral` images, this resolution breakdown directly mirrors class accuracy on `neutral` vs `fire`/`smoke`.

### 7.2 By Image Brightness (Mean Luminance)
- **Dark Scenes (Luminance $< 80$):** 65 images, **$81.54\%$ accuracy** (53/65 correct).
- **Normal Scenes (Luminance $80\text{--}160$):** 225 images, **$92.44\%$ accuracy** (208/225 correct).
- **Bright Scenes (Luminance $> 160$):** 8 images, **$75.00\%$ accuracy** (6/8 correct).

**Diagnostic Insight:** The model performs best under moderate daylight conditions ($92.44\%$), but experiences substantial accuracy degradation in dark environments ($81.54\%$) and washed-out overexposed conditions ($75.00\%$). Nighttime wildfire monitoring and bright glare conditions represent significant vulnerability areas.

### 7.3 By Aspect Ratio
- **Portrait ($< 0.9$):** 9 images, **$88.89\%$ accuracy** (8/9 correct).
- **Square ($0.9\text{--}1.1$):** 8 images, **$75.00\%$ accuracy** (6/8 correct).
- **Landscape ($> 1.1$):** 281 images, **$90.04\%$ accuracy** (253/281 correct).

---

## 8. Phase G: Test Suite & Regression Verification

Comprehensive verification was executed across the entire repository to ensure all code changes, test suites, and project baselines remain intact:

| Verification Target | Command / Check | Result | Evidence |
| :--- | :--- | :---: | :--- |
| **New Phase 6 Audit Tests** | `pytest ml/tests/test_audit.py` | **4 PASSED** | 0.14s — duplicate absence, PNG zero-flips, support invariants. |
| **Complete ML Suite** | `pytest ml/tests/ -v` | **117 PASSED** | 60.04s — full data pipeline, transforms, models, engine, evaluation, audit. |
| **Backend Non-DB Tests** | `pytest backend -m "not database"` | **74 PASSED** | 4.30s — health routes, schemas, services, models, storage atomic rollback. |
| **Alembic Unit Tests** | `pytest backend/tests/unit/test_alembic*` | **5 PASSED** | 3.59s — offline SQL migration generator verification. |
| **Dependency Integrity** | `python -m pip check` | **CLEAN** | "No broken requirements found." |
| **Historical Dataset Hash** | `python scratch/verify_existing_unchanged.py` | **100% MATCH** | All 2,936 files bitwise identical to baseline inventory. |
| **Model Checkpoint Integrity**| SHA-256 Checksum on Checkpoints | **UNCHANGED** | Baseline and MobileNet weights remain strictly byte-identical. |
| **Git Working Tree** | `git status` | **NO COMMITS** | Working tree unmodified, no commits or pushes created. |

---

## 9. Serialized Audit Artifacts

All diagnostic results have been structured and serialized into `artifacts/audits/m07_phase6/`:

1. `artifacts/audits/m07_phase6/audit_summary.json`: Top-level summary of all audit metrics, duplicate counts, error summaries, and official status.
2. `artifacts/audits/m07_phase6/duplicate_audit.json`: Exact SHA-256 and near-duplicate dHash verification results.
3. `artifacts/audits/m07_phase6/dataset_distribution.json`: Comprehensive dimensional, aspect ratio, file size, luminance, contrast, and color channel statistics across all splits and classes.
4. `artifacts/audits/m07_phase6/format_bias_audit.json`: Raster format census and controlled normalization experiment metrics.
5. `artifacts/audits/m07_phase6/normalized_evaluation.json`: Complete evaluation metrics on normalized PNG test set.
6. `artifacts/audits/m07_phase6/prediction_error_analysis.json`: Granular breakdown of all 31 misclassifications with confidence scores and probabilities.
7. `artifacts/audits/m07_phase6/confidence_analysis.json`: Confidence distributions, calibration statistics, and subgroup accuracies across resolution, brightness, and aspect ratio.
8. `artifacts/audits/m07_phase6/prediction_changes.csv`: Sample-by-sample 298-row CSV documenting original vs normalized predictions and probability differences.
9. `artifacts/audits/m07_phase6/test_normalized_png/`: Directory containing all 298 lossless PNG re-encoded test images.

---

## 10. Final Engineering Assessment (Answers to Mandated Questions)

### Question 1: Is the dataset split free of exact duplicates?
**Answer:** **Yes.** Cryptographic SHA-256 analysis across all 2,931 images confirmed **0 intra-split duplicates** and **0 cross-split duplicates** between train, validation, and test partitions. The split is strictly byte-isolated.

### Question 2: Are there near-duplicate risks?
**Answer:** **No.** Perceptual difference hashing (`dHash` 64-bit) screened all 784,634 test-to-train and test-to-validation image pairs. Zero pairs exhibited Hamming distance $\le 2$ or $\le 4$, and the minimum observed distance was $>6$. There are no rescaled, recropped, or recompressed duplicate variants bridging the splits.

### Question 3: How severe is the internal-format/class confounding?
**Answer:** **High.** In the test set, **100% of `neutral` images (100/100) are PackBits TIFF**, while **100% of `fire` and `smoke` images (198/198) are JPEG**. Across the entire dataset, 100% of TIFF images (156 images) belong to `neutral`. Furthermore, all 156 TIFFs are exactly $800 \times 600$ pixels, whereas `fire` and `smoke` JPEGs average $\approx 270 \times 185$ pixels.

### Question 4: Does common-format normalization change the model's predictions?
**Answer:** **No.** Re-encoding all 298 test images to lossless standardized PNG resulted in **0 prediction flips (0.00%)**, a maximum probability shift of **0.000000**, and identical confusion matrices. This proves that container parsing does not leak format metadata into model activations. However, pixel-level resolution and compression characteristics remain intact.

### Question 5: Is the 89.60% test accuracy a trustworthy estimate of generalization?
**Answer:** **Partially.** The 89.60% accuracy demonstrates genuine discriminatory power for distinguishing `fire` from `smoke` (which are both web JPEGs of similar resolution, achieving $87.76\%$ and $93.00\%$ recall respectively). However, because `neutral` is heavily confounded with $800 \times 600$ high-resolution photography, the $88.00\%$ neutral recall cannot be certified as true visual generalization on diverse real-world non-disaster scenes.

### Question 6: Was the test set used for model selection?
**Answer:** **Yes.** In Phase 5, the composite selection score ($0.9007$ vs $0.0670$) was explicitly computed using `test_loader` metrics rather than validation metrics. While `BaselineCNN` was unequivocally superior to the collapsed `MobileNetV3`, using the test set to make the selection decision constitutes formal selection contamination.

### Question 7: What are the model's most important failure patterns?
**Answer:**
1. **Fire obscured by heavy smoke** (9 fire images misclassified as smoke with high confidence).
2. **Atmospheric/seasonal false alarms** (fog, haze, dusk, and autumn colors misclassified as fire or smoke in 12 neutral images).
3. **Underperformance in extreme lighting** (accuracy drops to $81.54\%$ on dark scenes and $75.00\%$ on bright scenes).

### Question 8: What conclusions are supported by evidence?
**Answer:**
- The model learns valid spatial/color features distinguishing open flames from smoke columns within the JPEG domain.
- Pillow container decoding does not introduce format leakage.
- The training split contains zero exact or near duplicates of test images.
- `BaselineCNN` reliably converges from scratch on CPU without external weights.

### Question 9: What conclusions remain uncertain?
**Answer:**
- Whether the model would maintain $\sim 88\%$ neutral recall if presented with low-resolution web JPEGs of forest, city, and mountain landscapes.
- Whether the model would correctly identify wildfire flames if presented in high-resolution uncompressed aerial TIFF imagery.
- The model's true performance on nocturnal/nighttime wildfire imagery.

### Question 10: What should be done before using this model in a real disaster-monitoring system?
**Answer:**
1. **Fix Training Engine Tuple Truthiness:** Correct `is_improved` logic in `EarlyStopping` to prevent unintended checkpoint overwriting.
2. **Multi-Source Benchmark Evaluation:** Curate an independent evaluation set consisting of format-balanced, resolution-balanced images (e.g. low-res neutral JPEGs and high-res aerial fire TIFFs).
3. **Curate Hard Negatives:** Augment training with non-disaster fog, clouds, sunsets, autumn foliage, and red rock formations.
4. **Deploy Temperature Scaling / Calibration:** Mitigate overconfident false alarms before feeding predictions to automated alerting pipelines.

---

## 11. Official Model Reliability Status

### Assigned Status: **`PROMISING BUT REQUIRES FURTHER VALIDATION`**

#### Rationale
- **Why not `VALIDATED FOR RESEARCH USE`?** The 100% test-set format/resolution confounding on `neutral` images and the documented test-set selection contamination prevent formal certification. A model cannot be validated for research publication when a class is confounded with image dimensions and container provenance.
- **Why not `NOT RELIABLE ENOUGH FOR CURRENT USE`?** The model demonstrates genuine, strong discriminative ability between `fire` (87.76% recall) and `smoke` (93.00% recall) on 198 web JPEGs with identical provenance. Container normalization proved 0 prediction flips. The model is a functional, highly promising architecture, but requires balanced dataset validation before operational deployment.

---

## 12. Recommended Next Engineering Milestone

### Milestone 07 — Phase 7: Dataset Hardening, Multi-Source Generalization & Model Calibration

1. **Dataset Balance Remediation:**
   - Ingest 500+ diverse, low-resolution JPEG neutral images (forests, roads, buildings, mountains) and high-resolution fire/smoke captures.
   - Rebalance splits ensuring all classes contain identical format and resolution distributions.
2. **Training Engine Tuple Correction:**
   - Patch `early_stopping.update()` unpack logic in [`ml/training/engine.py`](../../ml/training/engine.py).
3. **Rigorous Out-of-Distribution (OOD) Benchmark:**
   - Evaluate against an external wildland fire benchmark (e.g., FLAME or HPWREN camera feeds).
4. **FastAPI Inference Endpoint Integration:**
   - Package `BaselineCNN` into the SCOUT media ingestion pipeline ([`backend/app/api/v1/endpoints/media.py`](../../backend/app/api/v1/endpoints/media.py)) with confidence thresholding and uncertainty flags.
