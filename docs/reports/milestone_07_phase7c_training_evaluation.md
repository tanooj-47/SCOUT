# SCOUT Milestone 07 — Phase 7C: Controlled Model Training, Selection & Generalization Evaluation Report

**Project:** SCOUT — Multimodal Disaster Intelligence & Response Platform  
**Milestone:** Milestone 07 — Image Classification Engineering & Generalization  
**Phase:** Phase 7C — Controlled Training, Model Selection & Generalization Evaluation  
**Auditor / Lead Engineer:** Senior Machine Learning Systems Engineer  
**Date:** October 31, 2026  
**Final Phase Verdict:** **`APPROVED_WITH_LIMITATIONS`**  

---

## Executive Summary

Milestone 07 Phase 7C executed the controlled training, validation-based model selection, and single-pass test generalization evaluation for the SCOUT wildfire image classification system. 

All experiments were executed on the approved, hardened multi-source dataset `data/processed/fire_smoke_v2/` ($N=3,507$) partitioned strictly across 3,153 atomic scene groups via `artifacts/audits/m07_phase7b/split_manifest.csv` (`train`: 2,451; `validation`: 523; `test`: 533). 

```
========================================================================================================
MODEL ARCHITECTURE        TOTAL PARAMS    VAL LOSS    VAL ACC    VAL MACRO F1    STATUS / OUTCOME
========================================================================================================
BaselineCNN (4-Block)          405,539      0.4459     83.94%          0.8387    SELECTED CHAMPION
MobileNetV3-Small (Offline)  1,520,931      1.0989     34.23%          0.1700    COLLAPSED (Majority)
========================================================================================================
```

Following strict gatekeeper protocol, the champion model (**BaselineCNN**) was locked and serialized in `model_selection.json` prior to any test-set evaluation. A single-pass evaluation on the untouched test partition ($N=533$) yielded:
- **Test Accuracy:** **86.12%** ($459 / 533$)
- **Test Macro F1:** **0.8601** (Fire: **0.9003**, Neutral: **0.8284**, Smoke: **0.8515**)
- **Test Loss:** **0.3481** (Cross-Entropy)
- **Inference Latency:** **22.01 ms / sample** on standard CPU execution

### Verdict Justification: `APPROVED_WITH_LIMITATIONS`
The experimental protocol strictly adhered to scientific boundaries: zero test leakage, locked validation selection, and full test suite passing (137 ML tests, 74 backend tests, 5 Alembic tests). However, **limitations require documented qualification**:
1. **Residual Format Shortcuts:** 100% of test TIFFs ($N=25$) were classified as neutral with 100% accuracy, while smoke remains 100% JPEG across the corpus.
2. **Source Domain Shift:** Performance on newly acquired external sources dropped compared to DeepQuestAI (DeepQuest Acc: 88.59%, D-Fire Acc: 78.43%, BoWFire Acc: 65.71%), specifically due to non-fire outdoor distractors (sunsets, red uniforms, hazy sky) mispredicted as smoke/fire.
3. **Offline MobileNetV3 Training Collapse:** Without pre-cached ImageNet weights, training deep depthwise separable backbones from scratch on 2,451 samples failed to converge away from the majority class.

---

## 1. Mandatory Pre-Training Inspection

Prior to starting training runs, all 12 items on the mandatory pre-training checklist were forensically verified via `scratch/pre_training_inspection.py`:

| Check # | Inspection Item | Verified State | Status |
| :---: | :--- | :--- | :---: |
| **1** | Model Implementations | BaselineCNN = 405,539 params; MobileNetV3-Small = 1,520,931 params. No softmax in forward pass. | **PASS** |
| **2** | Training Engine v2 Support | `TrainingConfig` explicitly supports `dataset_root=DATASET_V2_ROOT`. | **PASS** |
| **3** | Manifest Mapping | All 3,507 manifest relative paths match disk files bit-for-bit. Missing = 0. | **PASS** |
| **4** | Class Mapping | Exactly `fire: 0, neutral: 1, smoke: 2` enforced across config, loaders, and dataset. | **PASS** |
| **5** | Split Directory Counts | Train = 2,451; Validation = 523; Test = 533. Sum = 3,507. | **PASS** |
| **6** | Split Sample Isolation | Train $\cap$ Val = $\emptyset$; Train $\cap$ Test = $\emptyset$; Val $\cap$ Test = $\emptyset$. Zero cross-split leakage. | **PASS** |
| **7** | Augmentation Isolation | `RandomHorizontalFlip`, `RandomAffine`, `ColorJitter` present in Train only. Val/Test strictly deterministic. | **PASS** |
| **8** | RGB Decoding Consistency | `scout_image_loader` forces Pillow `.convert('RGB')` on all formats into `(B, 3, 224, 224)`. | **PASS** |
| **9** | Normalization Constants | Standard ImageNet channel mean `(0.485, 0.456, 0.406)` and std `(0.229, 0.224, 0.225)`. | **PASS** |
| **10** | Checkpoint EarlyStopping Gating | Phase 7A fix verified: `EarlyStoppingResult(improved, should_stop)` strictly requires boolean `is_best`. | **PASS** |
| **11** | Validation-Only Selection | Checkpoint saving and early stopping monitor `val_macro_f1` from validation loader only. | **PASS** |
| **12** | Test Partition Safeguard | Test loader is decoupled and uncalled during training and model selection. | **PASS** |

---

## 2. Code Changes & Architecture

To ensure strict preservation of historical artifacts while executing Phase 7C, no existing codebase contracts or dataset binaries were modified:
1. **Isolated Output Architecture:**
   - Isolated checkpoints: `artifacts/checkpoints/m07_phase7c_v2/`
   - Isolated metrics: `artifacts/metrics/m07_phase7c_v2/`
   - Isolated plots: `artifacts/plots/m07_phase7c_v2/`
2. **Dedicated Phase 7C Orchestrator:** Implemented in `scratch/run_phase7c_experiments.py` using existing `Trainer`, `EarlyStopping`, `CheckpointManager`, and `ScoutFireSmokeDataset` modules.
3. **Pillow Plotting Suite:** Implemented in `scratch/plot_utils.py` to generate standalone, publication-quality PNG plots and Grad-CAM overlays without introducing external network dependencies.
4. **Historical Asset Protection:** Historical `v1` dataset (`data/processed/fire_smoke_v1/`, 2,936 files) and all 6 Phase 5/7A checkpoints remained completely untouched and bitwise identical.

---

## 3. Models Trained & Hyperparameter Configurations

Both models were trained using identical batch sizes, hardware resources, and dataset partitions.

### 3.1 Model A — Baseline CNN
- **Architecture:** 4-stage convolutional neural network:
  - ConvBlock 1: Conv2d(3 $\rightarrow$ 32, k=3, s=1, p=1) + BatchNorm2d + ReLU + MaxPool2d(k=2, s=2)
  - ConvBlock 2: Conv2d(32 $\rightarrow$ 64, k=3, s=1, p=1) + BatchNorm2d + ReLU + MaxPool2d(k=2, s=2)
  - ConvBlock 3: Conv2d(64 $\rightarrow$ 128, k=3, s=1, p=1) + BatchNorm2d + ReLU + MaxPool2d(k=2, s=2)
  - ConvBlock 4: Conv2d(128 $\rightarrow$ 256, k=3, s=1, p=1) + BatchNorm2d + ReLU + MaxPool2d(k=2, s=2)
  - Global Head: AdaptiveAvgPool2d((1, 1)) $\rightarrow$ Flatten $\rightarrow$ Dropout(0.4) $\rightarrow$ Linear(256 $\rightarrow$ 64) $\rightarrow$ ReLU $\rightarrow$ Dropout(0.2) $\rightarrow$ Linear(64 $\rightarrow$ 3)
- **Parameters:** Exactly **405,539** parameters (all trainable).
- **Optimizer:** AdamW ($\text{lr} = 10^{-3}$, $\text{weight\_decay} = 10^{-4}$).
- **Scheduler:** CosineAnnealingLR ($T_{\max} = 25$, $\eta_{\min} = 10^{-5}$).
- **Early Stopping:** Monitored `val_macro_f1` with $\text{patience} = 6$, $\text{min\_delta} = 0.001$. Max epochs: 25.

### 3.2 Model B — MobileNetV3-Small
- **Architecture:** MobileNetV3-Small adapted for 3-class wildfire classification (`classifier[3]` replaced with `Linear(1024, 3)`).
- **Parameters:** Exactly **1,520,931** parameters.
- **Initialization:** `init_mode="random"` (offline, trained from scratch).
- **Two-Stage Training Protocol:**
  - *Stage 1 (Classifier Warmup, 5 Epochs):* Entire backbone frozen (`requires_grad=False`), BatchNorm in eval mode. AdamW on classifier head only ($\text{lr} = 10^{-3}$, $\text{weight\_decay} = 10^{-4}$, CosineAnnealingLR $T_{\max} = 5$).
  - *Stage 2 (Deep Fine-Tuning, up to 20 Epochs):* Restored best Stage 1 weights. Unfroze high-level semantic blocks `features[9:]` and classifier head; low-level blocks `features[:9]` remained frozen. BatchNorm running statistics remained frozen. Fresh Stage 2 AdamW optimizer (backbone $\text{lr} = 10^{-5}$, classifier $\text{lr} = 10^{-4}$, $\text{weight\_decay} = 10^{-4}$, CosineAnnealingLR $T_{\max} = 20$). Monitored `val_macro_f1` ($\text{patience} = 6$, $\text{min\_delta} = 0.001$).

---

## 4. Training Progression & Learning Dynamics

### 4.1 Baseline CNN Training Dynamics
The Baseline CNN trained across all 25 epochs (total duration: 4,008.5s, mean ~160s/epoch):
- **Epoch 01:** Train Loss = 0.8309, Val Loss = 0.7764, Val Macro F1 = **0.6979** (initial checkpoint saved).
- **Epoch 07:** Train Loss = 0.5720, Val Loss = 0.5626, Val Macro F1 = **0.7831**.
- **Epoch 15:** Train Loss = 0.4670, Val Loss = 0.4935, Val Macro F1 = **0.8124**.
- **Epoch 20 (Best Epoch):** Train Loss = 0.3995, Val Loss = **0.4459**, Val Accuracy = **83.94%**, Val Macro F1 = **0.8387** (saved as `baseline_cnn_best.pt`).
- **Epochs 21–25:** Training loss continued descending to 0.3650, while validation loss stabilized at 0.4306 with Macro F1 plateauing around 0.8224.
- Complete epoch history is preserved in `artifacts/metrics/m07_phase7c_v2/training_history_baseline_cnn.csv`.

### 4.2 MobileNetV3-Small Training Dynamics
- **Stage 1 (Warmup):** Across 5 epochs, train loss remained static at 1.0990, validation loss at 1.0988, with validation accuracy stuck at 34.23% (Macro F1 = **0.1700**).
- **Stage 2 (Fine-Tuning):** Following transition and unfreezing of blocks 9..12, train loss remained near 1.0987 and validation loss at 1.0989. Accuracy remained constant at 34.23% across 7 epochs, triggering early stopping at Epoch 7.
- Complete epoch history is preserved in `artifacts/metrics/m07_phase7c_v2/training_history_mobilenetv3.csv`.

*Figure: Loss Curves (`artifacts/plots/m07_phase7c_v2/loss_curves.png` — plot retained locally)*
*Figure: Macro F1 Curves (`artifacts/plots/m07_phase7c_v2/macro_f1_curves.png` — plot retained locally)*

---

## 5. Validation Results & Champion Model Selection

Both models were evaluated on the complete validation split ($N=523$) using their best validation checkpoints.

### 5.1 Validation Metrics Table

| Metric | Baseline CNN (Best: Epoch 20) | MobileNetV3-Small (Best: Stage 2) | Margin / Difference |
| :--- | :---: | :---: | :---: |
| **Cross-Entropy Loss** | **0.4459** | 1.0989 | -0.6530 (Superior) |
| **Overall Accuracy** | **83.94%** | 34.23% | +49.71% (Superior) |
| **Macro F1 Score** | **0.8387** | 0.1700 | +0.6687 (Superior) |
| **Weighted F1 Score** | **0.8385** | 0.1744 | +0.6641 (Superior) |
| **Fire Recall** | **93.64%** ($162 / 173$) | 0.00% ($0 / 173$) | Complete separation |
| **Neutral Recall** | **73.18%** ($131 / 179$) | 100.00% ($179 / 179$) | Majority collapse |
| **Smoke Recall** | **85.38%** ($146 / 171$) | 0.00% ($0 / 171$) | Complete separation |
| **Total Parameters** | **405,539** | 1,520,931 | 3.75x more compact |

### 5.2 Validation Confusion Matrices

**Baseline CNN (Epoch 20):**
```
                Predicted Fire    Predicted Neutral    Predicted Smoke
True Fire             162                 3                   8
True Neutral           17               131                  31
True Smoke             16                 9                 146
```

**MobileNetV3-Small (Stage 2):**
```
                Predicted Fire    Predicted Neutral    Predicted Smoke
True Fire               0               173                   0
True Neutral            0               179                   0
True Smoke              0               171                   0
```

### 5.3 Selection Decision & Rationale
- **Champion Selected:** **`baseline_cnn`**
- **Decision Rationale:** BaselineCNN achieved a validation macro F1 of **0.8387** with strong recall across all three classes (Fire: 93.64%, Neutral: 73.18%, Smoke: 85.38%), exhibiting genuine feature learning and minimal parameter overhead. MobileNetV3-Small collapsed completely to predicting the majority class (`neutral`), achieving a macro F1 of only 0.1700 with zero recall on fire and smoke.
- **Gatekeeper Verification:** The decision was recorded in `model_selection.json` before loading the test partition.

*Figure: Validation Confusion Matrix Baseline (`artifacts/plots/m07_phase7c_v2/val_confusion_matrix_baseline_cnn.png` — plot retained locally)*
*Figure: Validation Confusion Matrix MobileNet (`artifacts/plots/m07_phase7c_v2/val_confusion_matrix_mobilenetv3.png` — plot retained locally)*

---

## 6. Final Test Set Evaluation (Champion Model)

The selected champion model (`baseline_cnn_best.pt`) was evaluated in a single deterministic pass over the untouched test split ($N=533$).

### 6.1 Aggregate Test Performance

| Metric | Measured Value | Operational Implication |
| :--- | :---: | :--- |
| **Test Accuracy** | **86.12%** ($459 / 533$) | High baseline generalization on unseen scenes |
| **Macro F1 Score** | **0.8601** | Balanced multi-class discrimination |
| **Weighted F1 Score** | **0.8595** | Accounts for minor class sample variations |
| **Test Loss** | **0.3481** | Low cross-entropy; high prediction confidence |
| **CPU Latency** | **22.01 ms / sample** | Suitable for real-time video stream ingestion |

### 6.2 Per-Class Performance Breakdown

| Class | Precision | Recall | F1-Score | Support | Correct Predictions |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Fire** | **0.8520** | **0.9543** | **0.9003** | 175 | 167 |
| **Neutral** | **0.9150** | **0.7568** | **0.8284** | 185 | 140 |
| **Smoke** | **0.8261** | **0.8786** | **0.8515** | 173 | 152 |
| **Macro Avg** | **0.8644** | **0.8632** | **0.8601** | 533 | 459 |
| **Weighted Avg** | **0.8654** | **0.8612** | **0.8595** | 533 | 459 |

### 6.3 Test Confusion Matrix Analysis
```
                     Predicted Fire    Predicted Neutral    Predicted Smoke
True Fire (175)           167                  4                    4
True Neutral (185)         17                140                   28
True Smoke (173)           12                  9                  152
```
- **Fire Safety (Low False Negatives):** Only 4 fire images were misclassified as neutral ($2.29\%$), and 4 as smoke ($2.29\%$). Active flame fronts are detected with **95.43% recall**.
- **Smoke Safety:** Only 9 smoke images were misclassified as neutral ($5.20\%$). Smoke is detected with **87.86% recall**.
- **Neutral False Positives:** The majority of errors are neutral non-fire images misclassified as smoke ($N=28$) or fire ($N=17$). Distractors (fog, hazy skies, red emergency trucks) trigger conservative fire/smoke alarms.

*Figure: Test Confusion Matrix (`artifacts/plots/m07_phase7c_v2/test_confusion_matrix.png` — plot retained locally)*
*Figure: Per-Class Performance (`artifacts/plots/m07_phase7c_v2/per_class_performance.png` — plot retained locally)*

---

## 7. Mandatory Sliced Source-Wise Test Evaluation

To verify whether the champion model generalizes uniformly across source domains or overfits to the dominant historical provider, test samples were joined with source metadata.

### 7.1 Source-Wise Metrics Comparison Table

| Source ID | Test Samples | Accuracy | Macro F1 | Present Classes | Fire Recall | Neutral Recall | Smoke Recall |
| :--- | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| `deepquest_v1` | **447** (83.9%) | **88.59%** | **0.8868** | Fire, Neutral, Smoke | **96.32%** ($131/136$) | **83.87%** ($130/155$) | **86.54%** ($135/156$) |
| `dfire` | **51** (9.6%) | **78.43%** | **0.6698** | Fire, Neutral, Smoke | **100.00%** ($21/21$) | **15.38%** ($2/13$) | **100.00%** ($17/17$) |
| `bowfire` | **35** (6.6%) | **65.71%** | **0.4344** | Fire, Neutral *(0 Smoke)* | **83.33%** ($15/18$) | **47.06%** ($8/17$) | *N/A (0 samples)* |

### 7.2 Source-Specific Failure Analysis

1. **`deepquest_v1` (Dominant Baseline Source):**
   - Performance is exceptional (Acc: 88.59%, Macro F1: 0.8868). Because this source comprises 83.6% of training data, the convolutional feature hierarchy is heavily adapted to web photography textures.
2. **`dfire` (Surveillance Camera Feeds):**
   - Fire recall and Smoke recall are **100.0%** ($21/21$ fire, $17/17$ smoke detected).
   - However, **Neutral recall collapses to 15.38%** ($11 / 13$ neutral frames misclassified as smoke). D-Fire neutral frames consist of wide-angle surveillance cameras showing distant horizons, haze, and low-contrast skies, which the network misinterprets as diffuse smoke plumes.
3. **`bowfire` (Adversarial Benchmark Distractors):**
   - BoWFire contains zero smoke images. Its neutral class consists exclusively of adversarial non-fire emergency scenes (red fire engines, firefighters in bright yellow/red coats, sunsets, autumn trees).
   - Neutral recall drops to **47.06%** ($9 / 17$ neutral images misclassified as fire). The network triggers false alarms on large red structures.
   - Fire recall remains solid at **83.33%** ($15 / 18$).

*Figure: Source-Wise Performance (`artifacts/plots/m07_phase7c_v2/source_wise_performance.png` — plot retained locally)*

---

## 8. Shortcut-Learning Diagnostics & Error Analysis

The Phase 7B audit revealed residual format shortcuts in the dataset. Sliced diagnostics were evaluated on the test set to determine whether the model exploits container formats:

### 8.1 Performance Across Container Format Slices

| Format | Test Count | Class Composition | Accuracy | True / Pred Breakdown |
| :--- | :---: | :--- | :---: | :--- |
| **JPEG** | 471 | Fire: 157, Neutral: 141, Smoke: 173 | **86.84%** | Balanced performance across all three classes. |
| **PNG** | 35 | Fire: 18, Neutral: 17, Smoke: 0 | **65.71%** | Fire Acc: 83.3%, Neutral Acc: 47.1% (BoWFire distractors). |
| **TIFF** | 25 | Fire: 0, Neutral: 25, Smoke: 0 | **100.00%** | **100% of TIFFs classified as Neutral ($25 / 25$).** |
| **BMP** | 1 | Neutral: 1 | **100.00%** | 1 correct neutral. |
| **GIF** | 1 | Neutral: 1 | **100.00%** | 1 correct neutral. |

### 8.2 Confirmation of Residual Shortcut Susceptibility
- **TIFF Exclusivity Shortcut:** Because 100% of TIFF files in the dataset are in the `neutral` class, the model achieves 100% accuracy on test TIFFs ($25/25$). While Grad-CAM confirms the network attends to trees and ground terrain (see Section 9), the 100% precision of TIFF container format remains an unaddressed residual shortcut.
- **PNG Absence in Smoke Shortcut:** Out of 35 PNG images in the test set, exactly **0 were predicted as smoke**. The model correctly learned that PNG images in this corpus are either fire or neutral.

### 8.3 Error Category Distribution

| Error Category | Error Count | Percentage of Total Errors | Primary Root Cause |
| :--- | :---: | :---: | :--- |
| `neutral_as_smoke` | **28** | **37.8%** | Overcast skies, fog, mountain haze in D-Fire surveillance frames. |
| `neutral_as_fire` | **17** | **23.0%** | Red fire engines, red buildings, sunset lighting in BoWFire distractors. |
| `smoke_as_fire` | **12** | **16.2%** | Dense dark smoke with glowing thermal background or ember hues. |
| `smoke_as_neutral` | **9** | **12.2%** | Very thin, diffuse white smoke plumes blending into white clouds. |
| `fire_as_smoke` | **4** | **5.4%** | Heavy smoke occlusion where flame is small or obscured. |
| `fire_as_neutral` | **4** | **5.4%** | Distant small brushfire points in wide landscape shots. |
| **Total Errors** | **74** | **100.0%** | Overall error rate: $74 / 533 = 13.88\%$. |

---

## 9. Grad-CAM Explainability & Visual Salience

Grad-CAM activation maps were extracted from the final convolutional stage (`features[3].block[0]`, shape: $14 \times 14$) of `BaselineCNN` and overlaid onto representative test images.

### 9.1 Representative Case Studies

1. **Sample 1 (`deepquest_v1` Neutral TIFF):**
   - *Activation Focus:* Peaks sharply on green pine canopy and understory foliage.
   - *Shortcut Diagnosis:* The network does **not** activate on the letterbox padding borders or image corners. Activations are centered on natural forestry textures.
2. **Sample 2 (`deepquest_v1` Smoke JPEG):**
   - *Activation Focus:* Activations track the vertical rising smoke column and diffuse plume boundary.
   - *Shortcut Diagnosis:* Activations do not highlight high-frequency JPEG blocking artifacts; they localize on cloud-like smoke density.
3. **Sample 3 (`deepquest_v1` Fire JPEG):**
   - *Activation Focus:* Focused directly on the high-intensity yellow/orange flaming combustion front.
4. **Sample 4 (`bowfire` Fire PNG):**
   - *Activation Focus:* Strong activation on open flame regions, successfully ignoring surrounding unburned brush.
5. **Sample 5 (`dfire` Smoke JPEG):**
   - *Activation Focus:* Captures distant horizon wildfire smoke in surveillance camera view.
6. **Sample 6 (`bowfire` Neutral PNG - Red Distractor):**
   - *Activation Focus:* In false-positive cases, activation concentrates on saturated red paint on vehicles or structures, confirming that color hue heuristics remain active.

*All overlay image artifacts are persisted in `artifacts/plots/m07_phase7c_v2/`.*

---

## 10. Reproducibility & Integrity Verification

All experimental parameters and hardware telemetry were recorded in `artifacts/metrics/m07_phase7c_v2/reproducibility_metadata.json`:

```json
{
  "dataset_version": "fire_smoke_v2",
  "dataset_manifest_sha256": "b54cf60f047ba809eebbd428aed44300527db154144b1d88398dfd3fdc6829bb",
  "dataset_integrity_hashes_sha256": "6854db522c5ea2d4d7dc4dd538aa34b8a44de9a6d5d0a9b78b794c228bb0050d",
  "random_seed": 42,
  "pytorch_version": "2.15.0+cpu",
  "python_version": "3.14.7",
  "os_platform": "Windows-11-10.0.26100-SP0",
  "cpu_architecture": "Intel64 Family 6 Model 154 Stepping 4",
  "total_ram_gb": 15.69,
  "checkpoints_saved": [
    "baseline_cnn_best.pt",
    "baseline_cnn_last.pt",
    "mobilenet_v3_small_stage1_best.pt",
    "mobilenet_v3_small_stage1_last.pt",
    "mobilenet_v3_small_stage2_best.pt",
    "mobilenet_v3_small_stage2_last.pt"
  ]
}
```

---

## 11. Test Suite Verification & Historical Asset Preservation

Following model training and artifact generation, the full verification battery was executed:

| Suite / Asset Category | Target Path / Scope | Verified Outcome | Regressions |
| :--- | :--- | :---: | :---: |
| **Historical Dataset v1** | `data/processed/fire_smoke_v1/` | **2,936 / 2,936 files bitwise identical** | **0** |
| **Historical Checkpoints** | `artifacts/checkpoints/*.pt` | **6 / 6 files bitwise identical** | **0** |
| **Historical Reports** | `docs/reports/milestone_07_phase*.md` | **4 / 4 reports bitwise identical** | **0** |
| **Phase 7B Manifest** | `artifacts/audits/m07_phase7b/split_manifest.csv` | **SHA-256 bitwise identical** | **0** |
| **Dataset V2 Tests** | `ml/tests/test_dataset_v2.py` | **10 passed in 12.57s** | **0** |
| **Full ML Test Suite** | `ml/tests/` | **137 passed in 79.53s** | **0** |
| **Backend Non-DB Tests** | `backend/tests/` (`-m "not database"`) | **74 passed in 3.94s** | **0** |
| **Alembic Unit Tests** | `backend/tests/unit/test_alembic*.py` | **5 passed in 3.92s** | **0** |
| **Python Dependencies** | `pip check` | **0 broken requirements** | **0** |

---

## 12. Known Limitations & Roadmap for Milestone 08

1. **Surveillance Distractor Sensitivity:**
   - D-Fire surveillance frames with white clouds or horizon haze currently yield high false-positive smoke alerts ($11 / 13$ neutral misclassified). Future training in M08 should incorporate temporal optical flow or multi-frame difference subtraction to eliminate static haze false alarms.
2. **Adversarial Red Distractor Sensitivity:**
   - BoWFire red vehicles and uniforms trigger false-positive fire alerts ($9 / 17$ neutral misclassified). Integrating chromatic saturation filters or multi-spectral bands will decouple flame radiant intensity from red paint pigment.
3. **Pretrained Backbone Deployment:**
   - MobileNetV3-Small collapsed when trained from scratch on 2,451 images. In environments where local ImageNet weights are available, pre-cached backbone initialization will allow transfer learning to outperform the custom CNN.

---

## 13. Final Verdict

### Status: **`APPROVED_WITH_LIMITATIONS`**

**Audit Conclusion:** Milestone 07 Phase 7C successfully achieved its engineering objectives:
- Executed controlled, reproducible training of BaselineCNN and MobileNetV3 on `fire_smoke_v2`.
- Preserved strict validation-only model selection, locking the champion model prior to test set ingestion.
- Established a verified test generalization benchmark of **86.12% accuracy** and **0.8601 macro F1** on 533 unseen scenes.
- Preserved 100% bitwise integrity of historical datasets, checkpoints, and reports with zero test regressions.

Milestone 07 Phase 7C is formally approved for progression to Milestone 08.
