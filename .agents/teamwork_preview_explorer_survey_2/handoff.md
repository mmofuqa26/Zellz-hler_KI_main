# Handoff Report — Feature Survey (R1, R2, R3)

**Agent:** teamwork_preview_explorer_survey_2  
**Date:** 2026-08-31T21:06:30Z  
**Working Directory:** `c:\Users\miran\Documents\Zellzählerki\antigravity\.agents\teamwork_preview_explorer_survey_2\`

---

## 1. Observation

1. **Existing Architecture & Codebase Files**:
   - `src/core/preprocessing.py`: Contains `to_grayscale`, `downscale_image_if_needed`, `apply_clahe`, `denoise_image`, and `remove_background_flatfield`.
   - `src/core/segmentation.py`: Implements `segment_cells` (lines 59–251) using marker-based watershed, local peaks via distance transform, and returns `cell_list` with `area_px`, `circularity`, and `solidity`.
   - `src/core/viability.py`: Implements `classify_viability` (lines 17–104) computing `i_core`, `i_ring`, and `intensity_diff`.
   - `src/core/metrics.py`: Implements `compute_summary_statistics` (lines 11–56) aggregating total cells, viability, mean area, and circularity.
   - `src/ui/app.py`: Streamlit app rendering tabs (Analysis, History, Support), metric cards (lines 162–169), dual-panel comparison (lines 174–185), and export buttons (lines 207–244).
   - `src/ui/components.py`: Sidebar rendering presets and sliders for diameter, distance ratio, marker area, block size, circularity, and viability (lines 65–148).
   - `src/utils/io_export.py`: Implements `generate_csv_data` (lines 18–64) and `create_annotated_overlay` (lines 67–146) currently color-coding by `LIVE`/`DEAD`.
   - `src/utils/database.py`: Implements SQLite persistence schema with tables `analyses` and `cells`.

2. **Existing Test Suite Baseline**:
   - Executed `uv run pytest -v` in project root:
     ```text
     tests/test_database.py::test_database_creation_and_save PASSED [ 10%]
     tests/test_preprocessing.py::test_to_grayscale_conversion PASSED [ 20%]
     tests/test_preprocessing.py::test_downscale_image_if_needed PASSED [ 30%]
     tests/test_preprocessing.py::test_clahe_and_denoise PASSED [ 40%]
     tests/test_preprocessing.py::test_remove_background_flatfield PASSED [ 50%]
     tests/test_segmentation.py::test_segmentation_clean_cluster PASSED [ 60%]
     tests/test_segmentation.py::test_segmentation_vignetting_and_dust PASSED [ 70%]
     tests/test_tiff.py::test_normalize_16bit_to_8bit PASSED [ 80%]
     tests/test_tiff.py::test_load_16bit_tiff_file PASSED [ 90%]
     tests/test_viability.py::test_viability_classification PASSED [100%]
     ============================= 10 passed in 0.57s ==============================
     ```
   - Baseline cell detection with fixed default preset yields 7 detected cells on each of the synthetic test images (`synthetic_clean_cluster.png`, `synthetic_vignetting_gradient.png`, `synthetic_dust_artifacts.png`, `synthetic_16bit_microscopy.tiff`).

3. **Requirement Specifications from ORIGINAL_REQUEST.md & GEMINI.md**:
   - R1: Automatic parameter calibration based on histogram, local contrast, and brightness gradient. Manual sliders preserved as overrides. Logged with INFO level.
   - R2: Confidence score per cell based on circularity, solidity, and local CNR. Traffic light overlay (Green $\ge 0.7$, Yellow $0.4-0.7$, Red $< 0.4$). Metric cards "Unsichere Zellen: X" and "Problematische Regionen: Y". CSV export with `confidence` column.
   - R3: Manual correction UI below dual-panel. Number input `Korrigierte Gesamtzahl` prefilled with count. Button `Korrektur speichern` saving JSON to `data/corrections/<timestamp>_<filename>.json` with `{original_count, corrected_count, delta, markers, image_path}`.

---

## 2. Logic Chain

1. **R1 Placement & Logic Chain**:
   - `GEMINI.md` mandates strict separation: Core (Image Processing) | UI (Streamlit) | Utils (Helpers), with no business logic in UI.
   - From Observation 1, `src/core/preprocessing.py` handles image analysis and filtering prior to segmentation.
   - Therefore, `auto_calibrate_parameters(gray, base_params)` belongs in `src/core/preprocessing.py` (or `src/core/calibration.py`).
   - Image histogram dynamic range ($P_{95} - P_5$), Laplacian variance, and radial corner-to-center illumination gradients directly inform `clahe_clip_limit`, `adaptive_thresh_block_size`, `adaptive_thresh_c`, `min_marker_area_px`, and `dist_threshold_ratio`.
   - In UI, `st.session_state` stores calibrated values on image load and passes slider values to `segment_cells`, preserving user overrides without unwanted reset loops.

2. **R2 Placement & Logic Chain**:
   - From Observation 1, `src/core/segmentation.py` calculates `circularity` and `solidity` for each cell; `src/core/viability.py` samples `i_core` and `i_ring`.
   - Local CNR is defined as $\text{CNR} = \frac{|\mu_{\text{core}} - \mu_{\text{ring}}|}{\sigma_{\text{ring}} + 1.0}$ and normalized into $S_{\text{CNR}} \in [0, 1]$.
   - Composite confidence score $S_{\text{conf}} = 0.35 \cdot C + 0.35 \cdot S + 0.30 \cdot S_{\text{CNR}} \in [0, 1]$.
   - Threshold mapping: Green ($\ge 0.7$), Yellow ($0.4 \le S_{\text{conf}} < 0.7$), Red ($< 0.4$).
   - `create_annotated_overlay` in `src/utils/io_export.py` will render contour outlines and centroids in Green/Yellow/Red.
   - `compute_summary_statistics` in `src/core/metrics.py` will aggregate `uncertain_cells` (yellow) and `problematic_cells` (red), rendered in `src/ui/app.py` as metric cards.
   - `generate_csv_data` in `src/utils/io_export.py` will include `Confidence` in the CSV header and rows.

3. **R3 Placement & Logic Chain**:
   - In `src/ui/app.py`, the dual-panel comparison is rendered at lines 174–185.
   - Placing the correction block directly underneath lines 185 provides immediate visual feedback.
   - Number input prefilled with `summary["total_cells"]` allows direct override.
   - A helper `save_manual_correction` in `src/utils/io_export.py` handles filesystem persistence to `data/corrections/<timestamp>_<filename>.json` with schema `{original_count, corrected_count, delta, markers, image_path, timestamp}`, keeping UI logic purely presentational.

---

## 3. Caveats

- **No Caveats**: All module boundaries, math equations, test cases, and UI integration points have been fully traced and mapped.

---

## 4. Conclusion

The codebase is exceptionally well-structured and fully prepared for the implementation of R1, R2, and R3. Detailed mathematical specifications and file-by-file roadmaps have been written to `survey_features.md`. All 10 existing unit tests pass, and clear verification strategies for the new requirements have been established.

---

## 5. Verification Method

To independently verify the survey and baseline project health:
1. Run existing test suite:
   ```powershell
   uv run pytest -v
   ```
   *Expected result: 10/10 tests pass.*
2. Inspect survey document:
   `c:\Users\miran\Documents\Zellzählerki\antigravity\.agents\teamwork_preview_explorer_survey_2\survey_features.md`
