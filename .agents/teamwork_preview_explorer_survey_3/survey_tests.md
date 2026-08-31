# Survey Report: Testing Suite & Validation Baseline
**Agent**: `teamwork_preview_explorer_survey_3`  
**Date**: 2026-08-31  
**Project**: CellCounter Pro (Zellzähler KI)  
**Status**: Completed  

---

## 1. Executive Summary

This report presents an in-depth audit of the existing testing suite, test fixtures, test images, baseline cell counting performance, and designs the verification strategy and new unit test specifications for the upcoming extensions:
1. **R1. Automatic Parameter Calibration per Image**
2. **R2. Confidence Traffic Light (Konfidenz-Ampel) per Cell Region**
3. **R3. Manual Correction UI & JSON Persistence**

### Key Findings
- **Current Test Suite**: 5 test files containing exactly **10 unit tests**.
- **Test Status**: **10/10 tests PASS** cleanly via `pytest -v` in **2.78s**.
- **Test Images in `tests/data/`**: 4 synthetic datasets (3 PNGs representing clean, vignetted/gradient, and dusty/noisy brightfield conditions, plus 1 16-bit TIFF).
- **Baseline Count on 3 Test Images (Fixed `Standard_Brightfield` Preset)**:
  - `synthetic_clean_cluster.png`: **7 cells** (Ground Truth: 13 cells -> 5 isolated cells + 2 merged clusters)
  - `synthetic_vignetting_gradient.png`: **7 cells** (Ground Truth: 13 cells -> 5 isolated cells + 2 merged clusters)
  - `synthetic_dust_artifacts.png`: **7 cells** (Ground Truth: 13 cells -> 5 isolated cells + 2 merged clusters)
- **Auto-Calibration Target**: Auto-calibration MUST detect **>= 7 cells** on each of the 3 test images without manual slider adjustments.

---

## 2. Inventory of Existing Tests & Fixtures

### 2.1 Test File Breakdown

| Test File | Test Case | Fixtures Used | Purpose & Verification Logic |
|---|---|---|---|
| `tests/test_preprocessing.py` | `test_to_grayscale_conversion` | None | Tests RGB (100x100x3) and RGBA (100x100x4) conversion to 2D uint8 grayscale. |
| `tests/test_preprocessing.py` | `test_downscale_image_if_needed` | None | Verifies downscaling of 4000x3000 -> 2000x1500 (factor 0.5) and no-op on 1000x800. |
| `tests/test_preprocessing.py` | `test_clahe_and_denoise` | None | Validates `apply_clahe` (clip_limit=2.0) and `denoise_image` (kernel_size=5). |
| `tests/test_preprocessing.py` | `test_remove_background_flatfield` | None | Tests Top-Hat morphology background subtraction on flatfield arrays. |
| `tests/test_segmentation.py` | `test_segmentation_clean_cluster` | `setup_test_images` | Loads `synthetic_clean_cluster.png`, runs CLAHE+denoise+`segment_cells`. Asserts $7 \le \text{cells} \le 16$, checks dictionary keys (`x_px`, `y_px`, `area_px`, `circularity`), and circularity $> 0.3$. |
| `tests/test_segmentation.py` | `test_segmentation_vignetting_and_dust` | `setup_test_images` | Tests `segment_cells` on `synthetic_vignetting_gradient.png` and `synthetic_dust_artifacts.png`. Asserts $\ge 7$ cells detected for each. |
| `tests/test_viability.py` | `test_viability_classification` | `setup_test_images` | Tests local background subtraction ($I_{\text{core}} - I_{\text{ring}}$) on `synthetic_clean_cluster.png`. Asserts presence of both `LIVE` and `DEAD` cells, $0 < \text{viability\_pct} < 100$. |
| `tests/test_database.py` | `test_database_creation_and_save` | `tmp_path` | Initializes SQLite DB, saves analysis results with 2 cells, queries history, and validates persisted records. |
| `tests/test_tiff.py` | `test_normalize_16bit_to_8bit` | None | Tests percentile normalization from uint16 array to uint8 $[0, 255]$. |
| `tests/test_tiff.py` | `test_load_16bit_tiff_file` | `setup_test_images` | Loads `synthetic_16bit_microscopy.tiff`, verifies 8-bit conversion and metadata dictionary (`is_tiff=True`, `original_dtype='uint16'`). |

### 2.2 Test Fixtures Architecture
- **`setup_test_images`**: Module-scoped fixture implemented in `test_segmentation.py`, `test_viability.py`, and `test_tiff.py`. Calls `create_all_test_images("tests/data")` from `tests.generate_test_images` to ensure test images exist dynamically.
- **`tmp_path`**: Pytest built-in fixture used in `test_database.py` to isolate SQLite database file writes.

### 2.3 Existing Test Suite Execution Result
```
pytest -v
============================= test session starts =============================
platform win32 -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\miran\Documents\Zellzählerki\antigravity
collected 10 items

tests/test_database.py::test_database_creation_and_save PASSED           [ 10%]
tests/test_preprocessing.py::test_to_grayscale_conversion PASSED         [ 20%]
tests/test_preprocessing.py::test_downscale_image_if_needed PASSED       [ 30%]
tests/test_preprocessing.py::test_clahe_and_denoise PASSED               [ 40%]
tests/test_preprocessing.py::test_remove_background_flatfield PASSED     [ 50%]
tests/test_segmentation.py::test_segmentation_clean_cluster PASSED       [ 60%]
tests/test_segmentation.py::test_segmentation_vignetting_and_dust PASSED [ 70%]
tests/test_tiff.py::test_normalize_16bit_to_8bit PASSED                  [ 80%]
tests/test_tiff.py::test_load_16bit_tiff_file PASSED                     [ 90%]
tests/test_viability.py::test_viability_classification PASSED            [100%]

============================= 10 passed in 2.78s ==============================
```

---

## 3. Test Images Analysis (`tests/data/`)

The synthetic images generated by `tests/generate_test_images.py` are parameterized as follows:

| Image Name | Format & Dimensions | Background & Illumination Model | Noise & Artifact Model | Ground Truth Cell Content |
|---|---|---|---|---|
| `synthetic_clean_cluster.png` | 8-bit PNG (800x600 px) | Uniform base gray level (215 / 255) | None (Clean background) | 13 cells:<br>• 5 isolated ($r \in [14, 20]$)<br>• 1 cluster of 3 cells<br>• 1 cluster of 5 cells<br>(9 Live, 4 Dead) |
| `synthetic_vignetting_gradient.png` | 8-bit PNG (800x600 px) | Radial quadratic vignette ($\text{strength}=0.60$, center $(400, 300)$) $\times$ Linear horizontal gradient ($1.1 \to 0.55$) | Illumination gradient (Mean: 141.04, Std: 36.07, Vignette ratio: 1.47) | Same 13 cells under severe illumination variations |
| `synthetic_dust_artifacts.png` | 8-bit PNG (800x600 px) | Uniform base gray level (215 / 255) | Gaussian noise ($\sigma=5$) + 40 dark dust specks ($r \in [1, 3]$, intensity $10\text{--}50$). Laplacian var: 1155.45 | Same 13 cells with high-frequency noise and dust |
| `synthetic_16bit_microscopy.tiff` | 16-bit uncompressed TIFF (800x600 px, uint16) | High dynamic range baseline (55,000 / 65,535) | Scaled 16-bit intensity values | Same 13 cells in 16-bit dynamic range |

### Statistical Profiles of Test Images

```
Image: Clean Cluster (tests/data/synthetic_clean_cluster.png)
  - Mean: 213.57, Std: 16.91, P10: 215, P50: 215, P90: 215
  - Laplacian Variance: 496.04, Gradient Magnitude: 64.94, Vignette Ratio: 0.99

Image: Vignetting Gradient (tests/data/synthetic_vignetting_gradient.png)
  - Mean: 141.04, Std: 36.07, P10: 86, P50: 148, P90: 181
  - Laplacian Variance: 371.32, Gradient Magnitude: 85.71, Vignette Ratio: 1.47

Image: Dust Artifacts (tests/data/synthetic_dust_artifacts.png)
  - Mean: 213.33, Std: 18.71, P10: 209, P50: 215, P90: 221
  - Laplacian Variance: 1155.45, Gradient Magnitude: 236.40, Vignette Ratio: 0.99
```

---

## 4. Baseline Cell Counting Behavior Analysis

### 4.1 Quantitative Comparison Across Presets

We executed the segmentation and viability pipelines on all test images using the three built-in configuration presets:

| Image | `Standard_Brightfield` (Default) | `Trypan_Blue_Viability` | `High_Density_Yeast` |
|---|---|---|---|
| `synthetic_clean_cluster.png` | **7 cells** (3 Live, 4 Dead) | **7 cells** (3 Live, 4 Dead) | **5 cells** (5 Live, 0 Dead) |
| `synthetic_vignetting_gradient.png` | **7 cells** (4 Live, 3 Dead) | **7 cells** (4 Live, 3 Dead) | **5 cells** (5 Live, 0 Dead) |
| `synthetic_dust_artifacts.png` | **7 cells** (4 Live, 3 Dead) | **7 cells** (5 Live, 2 Dead) | **0 cells** (0 Live, 0 Dead) |
| `synthetic_16bit_microscopy.tiff` | **1 cell** (1 Live, 0 Dead) | **5 cells** (5 Live, 0 Dead) | **3 cells** (3 Live, 0 Dead) |

### 4.2 Why Does the Baseline Detect 7 Cells (Ground Truth = 13)?
1. **Isolated Cells (5/5 detected)**:
   - $(100, 100)$, $(200, 100)$, $(300, 150)$, $(450, 120)$, $(600, 130)$ are segmented as individual cells with circularity $> 0.82$, solidity $> 0.95$.
2. **Clustered Cells (8 cells merged into 2 composite regions)**:
   - **Cluster 1 (3 touching cells at $(200, 300)$, $(225, 305)$, $(212, 330)$)**:
     - Distance transform with `dist_threshold_ratio = 0.25` and `peak_kernel_size = 9` produces a single unified seed.
     - Area $\approx 2137 \text{ px}$, circularity $\approx 0.603$, solidity $\approx 0.880$.
   - **Cluster 2 (5 dense cells at $(450, 400)$, $(475, 405)$, $(460, 430)$, $(490, 425)$, $(435, 420)$)**:
     - Seed detection merges the cluster into a single large object.
     - Area $\approx 3571 \text{ px}$, circularity $\approx 0.669$, solidity $\approx 0.914$.

### 4.3 Validation Baseline Target
- **Established Baseline**: The default fixed configuration (`Standard_Brightfield`) yields **7 cells** on each of the 3 test images (`synthetic_clean_cluster.png`, `synthetic_vignetting_gradient.png`, `synthetic_dust_artifacts.png`).
- **Acceptance Criterion Requirement**: Under Auto-Calibration (R1), without manual user intervention, the algorithm MUST detect **$\ge 7$ cells** on all 3 images.

---

## 5. Confidence Score Distribution on Test Images

Evaluating the proposed multi-factor confidence formulation on the baseline segmentation reveals clear separation:

$$\text{Confidence} = w_{\text{circ}} \cdot \text{Circularity} + w_{\text{solid}} \cdot \text{Solidity} + w_{\text{cnr}} \cdot \text{CNR}_{\text{norm}}$$

| Cell Description | Coordinates | Circularity | Solidity | CNR Score | Confidence Score | Traffic Light |
|---|---|---|---|---|---|---|
| Single Cell #1 (Dead) | $(200, 100)$ | 0.877 | 0.974 | 1.000 | **0.876** | 🟢 Green ($\ge 0.70$) |
| Single Cell #2 (Live) | $(100, 100)$ | 0.823 | 0.957 | 0.925 | **0.791** | 🟢 Green ($\ge 0.70$) |
| Single Cell #3 (Live) | $(450, 120)$ | 0.877 | 0.974 | 0.830 | **0.825** | 🟢 Green ($\ge 0.70$) |
| Single Cell #4 (Dead) | $(600, 130)$ | 0.892 | 0.970 | 1.000 | **0.880** | 🟢 Green ($\ge 0.70$) |
| Single Cell #5 (Live) | $(300, 150)$ | 0.892 | 0.970 | 0.790 | **0.816** | 🟢 Green ($\ge 0.70$) |
| Cluster 1 (3 Cells) | $(212.9, 310.5)$ | 0.603 | 0.880 | 0.270 | **0.599** | 🟡 Yellow ($0.40\text{--}0.70$) |
| Cluster 2 (5 Cells) | $(461.1, 415.6)$ | 0.669 | 0.914 | 0.210 | **0.617** | 🟡 Yellow ($0.40\text{--}0.70$) |

### Insights for Traffic Light Metrics:
- **Clean Isolated Cells**: Consistently scored between **$0.79\text{--}0.88$ (Green)**.
- **Merged Cell Clusters**: Scored between **$0.55\text{--}0.62$ (Yellow - Unsichere Zellen)** due to lower circularity and lower edge CNR.
- **Dust/Noise Specks**: If segmented, have low circularity, small area, and low CNR, scoring **$< 0.40$ (Red - Problematische Regionen)**.

---

## 6. Required New Unit Tests & Test Plan Design

To satisfy the acceptance criteria (at least 2 new unit tests, plus comprehensive regression verification), we design the following test suites:

### 6.1 Test Suite 1: `tests/test_calibration.py` (Auto-Calibration)

| Test Function | Target Function | Test Specification & Assertions |
|---|---|---|
| `test_analyze_image_statistics` | `src.core.calibration.analyze_image_statistics` | • Evaluates statistical feature extraction on flat, gradient, and noisy images.<br>• Asserts `vignette_ratio > 1.2` for `synthetic_vignetting_gradient.png` vs $\approx 1.0$ for clean image.<br>• Asserts `laplacian_var > 800` for `synthetic_dust_artifacts.png` vs $< 600$ for clean image.<br>• Asserts all returned keys are present (`mean`, `std`, `p10`, `p90`, `laplacian_var`, `gradient_mag`, `vignette_ratio`). |
| `test_auto_calibration_parameter_bounds` | `src.core.calibration.auto_calibrate_parameters` | • Runs auto-calibration on various image types.<br>• Asserts parameters stay within safe bounds:<br>  $1.0 \le \text{clahe\_clip\_limit} \le 5.0$, $11 \le \text{adaptive\_thresh\_block\_size} \le 35$, $2 \le \text{adaptive\_thresh\_c} \le 8$, $0.15 \le \text{dist\_threshold\_ratio} \le 0.40$, $1 \le \text{min\_marker\_area\_px} \le 8$. |
| `test_auto_calibration_cell_count_baseline` | `src.core.calibration.auto_calibrate_parameters` + `segment_cells` | • **Direct Acceptance Criterion Test**: Runs auto-calibration on the 3 test images (`synthetic_clean_cluster.png`, `synthetic_vignetting_gradient.png`, `synthetic_dust_artifacts.png`).<br>• Runs segmentation using calibrated parameters.<br>• Asserts $\text{len(cells)} \ge 7$ on every single test image. |
| `test_auto_calibration_logging` | `src.core.calibration.auto_calibrate_parameters` | • Uses `caplog` fixture to verify INFO-level log messages are emitted containing calibrated parameter values. |

### 6.2 Test Suite 2: `tests/test_confidence.py` (Confidence Scoring & Metrics)

| Test Function | Target Function | Test Specification & Assertions |
|---|---|---|
| `test_compute_confidence_score_synthetic` | `src.core.confidence.compute_cell_confidence` | • Generates synthetic contours (perfect circle, ellipse, star-shaped / jagged blob).<br>• Asserts score is normalized strictly in $[0.0, 1.0]$.<br>• Asserts circularity/solidity weighting penalizes distorted shapes.<br>• Asserts perfect circle gets score $\ge 0.70$ (Green), while jagged blob gets $< 0.40$ (Red). |
| `test_confidence_traffic_light_assignment` | `src.core.confidence.get_confidence_category` | • Asserts score $0.85 \to \text{"GREEN"}$, $0.55 \to \text{"YELLOW"}$, $0.25 \to \text{"RED"}$.<br>• Boundary checks: exactly $0.70 \to \text{"GREEN"}$, $0.40 \to \text{"YELLOW"}$, $0.399 \to \text{"RED"}$. |
| `test_metrics_summary_with_confidence` | `src.core.metrics.compute_summary_statistics` | • Feeds cell list with confidence scores to `compute_summary_statistics`.<br>• Asserts summary includes `unsichere_zellen` (Yellow + Red) and `problematische_regionen` (Red). |
| `test_csv_export_with_confidence_column` | `src.utils.io_export.export_to_csv` | • Exports cell list containing confidence scores to CSV.<br>• Asserts `'confidence'` and `'confidence_category'` columns exist in output CSV header and content. |

### 6.3 Test Suite 3: `tests/test_corrections.py` (Manual Correction Persistence)

| Test Function | Target Function | Test Specification & Assertions |
|---|---|---|
| `test_save_manual_correction_json` | `src.utils.database.save_manual_correction` (or `io_export.py`) | • Saves correction with `original_count=7`, `corrected_count=13`, `delta=6`, marker list, and image path.<br>• Asserts file is written to `data/corrections/<timestamp>_<filename>.json`.<br>• Asserts JSON schema contains all 5 required fields: `original_count`, `corrected_count`, `delta`, `markers`, `image_path`. |

---

## 7. Verification Strategy & Execution Roadmap

```
                                  VERIFICATION ROADMAP
+--------------------+      +-----------------------+      +---------------------------+
| 1. Pre-Change Run  | ---> | 2. Implementation &   | ---> | 3. Regression & Criterion |
| 10/10 Tests Pass   |      | New Unit Tests (8+)   |      | pytest -v (>= 18 Tests)   |
+--------------------+      +-----------------------+      +---------------------------+
                                                                         |
                                                                         v
                                                           +---------------------------+
                                                           | 4. Calibration Validation |
                                                           | Clean: >= 7 cells         |
                                                           | Vignette: >= 7 cells      |
                                                           | Dust: >= 7 cells          |
                                                           +---------------------------+
```

1. **Step 1: Baseline Integrity Verification**
   - Execute `pytest -v` before applying modifications. Expected: 10/10 passing.
2. **Step 2: Core Algorithm Unit Tests**
   - Implement `tests/test_calibration.py`, `tests/test_confidence.py`, and `tests/test_corrections.py`.
   - Run unit tests independently during development.
3. **Step 3: Acceptance Criteria Validation**
   - Verify that auto-calibration parameter auto-tuning logs at INFO level.
   - Verify that auto-calibration yields $\ge 7$ cells on each of the 3 test images.
   - Verify CSV export and JSON correction persistence formats.
4. **Step 4: Full Suite Pytest Verification**
   - Execute `pytest -v`.
   - Total test count should increase from 10 to $\ge 18$ tests, all passing with zero errors.
