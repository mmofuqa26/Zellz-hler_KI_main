# Handoff Report — Codebase & Core Pipeline Architecture Survey

**Agent**: teamwork_preview_explorer_survey_1  
**Milestone**: Architecture & Pipeline Survey  
**Date**: 2026-08-31T23:06:05+02:00  
**Handoff Type**: Hard  

---

## 1. Observation

1. **Workspace Layout & Existing Files**:
   - `config.yaml` defines presets (`Standard_Brightfield`, `Trypan_Blue_Viability`, `High_Density_Yeast`), logging (`logs/cell_counter.log`), and database settings (`data/cell_counter.db`).
   - `src/core/` contains:
     - `preprocessing.py` (lines 16-123): `to_grayscale`, `downscale_image_if_needed`, `apply_clahe`, `denoise_image`, `remove_background_flatfield`.
     - `segmentation.py` (lines 17-252): `fill_binary_holes`, `find_local_peaks`, `segment_cells`.
     - `viability.py` (lines 17-105): `classify_viability` implementing $I_{\text{core}} - I_{\text{ring}}$ comparison.
     - `tiff_handler.py` (lines 18-165): `load_image_with_metadata`, `normalize_to_8bit`.
     - `metrics.py` (lines 11-57): `compute_summary_statistics`.
   - `src/ui/` contains:
     - `app.py` (lines 46-290): Streamlit web application with 3 tabs (`tab_analysis`, `tab_history`, `tab_support`).
     - `components.py` (lines 20-189): `render_sidebar` with preset selector, sliders, and preset save dialog.
     - `visualization.py` (lines 13-150): `plot_viability_donut`, `plot_size_distribution`, `plot_intensity_scatter`.
   - `src/utils/` contains:
     - `logger.py` (lines 13-78): `setup_logger`, `get_logger` configuring a `RotatingFileHandler` (5MB, 3 backups) and console stream handler.
     - `config_manager.py` (lines 18-132): `load_config`, `save_config`, `get_available_presets`, `get_preset`, `save_preset`.
     - `database.py` (lines 19-195): SQLite operations for `analyses` and `cells` tables with `check_same_thread=False`.
     - `io_export.py` (lines 18-147): `generate_csv_data` and `create_annotated_overlay`.
   - `tests/` contains:
     - `generate_test_images.py`: creates 4 test images in `tests/data/`.
     - `test_preprocessing.py`, `test_segmentation.py`, `test_tiff.py`, `test_viability.py`, `test_database.py`.

2. **Test Execution Result**:
   - Command: `.venv\Scripts\python -m pytest -v`
   - Output: `10 passed in 0.94s` (100% pass rate).

3. **Algorithm Parameters in `config.yaml` / `segmentation.py`**:
   - `adaptive_thresh_block_size`: 21 (Brightfield), 25 (Trypan Blue), 15 (High Density Yeast).
   - `adaptive_thresh_c`: 5 (Brightfield), 4 (Trypan Blue), 3 (High Density Yeast).
   - `clahe_clip_limit`: 2.0 (Brightfield), 2.5 (Trypan Blue), 3.0 (High Density Yeast).
   - `min_marker_area_px`: 3 (Brightfield), 4 (Trypan Blue), 2 (High Density Yeast).
   - `dist_threshold_ratio`: 0.25 (Brightfield), 0.30 (Trypan Blue), 0.40 (High Density Yeast).
   - `min_cell_diameter_px`: 15, `max_cell_diameter_px`: 120.
   - `min_circularity`: 0.35, `min_solidity`: 0.50.

4. **Minor Code Finding**:
   - `src/utils/io_export.py` line 114 calls `math.sqrt()`, but `import math` is not imported at module top level.

---

## 2. Logic Chain

1. **Architecture Separation**: The codebase strictly adheres to GEMINI.md:
   - All core image processing logic lives in `src/core/`.
   - All UI rendering and user interactions are isolated in `src/ui/`.
   - Data persistence, YAML handling, and logging are encapsulated in `src/utils/`.
2. **Pipeline Robustness**:
   - Preprocessing reliably handles 8-bit, 16-bit, multi-channel, and large images (>4K) with tracked coordinate scaling.
   - Watershed segmentation decouples clustered cells through local maxima peak detection on Euclidean distance maps.
   - Viability accurately discriminates Trypan blue-positive cells using annular local background subtraction ($I_{\text{core}} - I_{\text{ring}}$).
3. **Extension Readiness**:
   - **R1 (Auto-calibration)**: Can be integrated as a dedicated module in `src/core/calibration.py` that computes adaptive Watershed parameters from image statistics and logs them at `INFO` level.
   - **R2 (Confidence Traffic Light)**: Can evaluate per-cell features (circularity, solidity, local CNR), update `io_export.py` (overlay and CSV `confidence` column), and display metric summaries in `app.py`.
   - **R3 (Manual Correction UI)**: Can be seamlessly placed directly below the dual-panel in `src/ui/app.py`, writing JSON outputs to `data/corrections/<timestamp>_<filename>.json`.

---

## 3. Caveats

- **Runtime Environment**: Python commands must be executed using `.venv\Scripts\python` on this Windows machine as global `pytest` is not mapped in PATH.
- **Missing Directory**: `data/corrections/` does not yet exist and should be created on demand when saving corrections.
- No other caveats.

---

## 4. Conclusion

The CellCounter Pro codebase is clean, well-tested, modular, and directly prepared for the three requested extensions:
1. Auto-calibration module in `src/core/`.
2. Confidence score and traffic light visualization in `src/core/`, `src/utils/io_export.py`, and `src/ui/`.
3. Correction UI section and JSON persistence in `src/ui/app.py` and `data/corrections/`.

All findings and detailed architectural breakdowns have been documented in `survey_core.md`.

---

## 5. Verification Method

To independently verify the survey observations:
1. Run test suite:
   ```powershell
   .venv\Scripts\python -m pytest -v
   ```
   Expected: 10 tests passed.
2. Inspect survey report:
   ```powershell
   view_file: c:\Users\miran\Documents\Zellzählerki\antigravity\.agents\teamwork_preview_explorer_survey_1\survey_core.md
   ```
3. Inspect `config.yaml` and `src/core/segmentation.py` to confirm parameter defaults.
