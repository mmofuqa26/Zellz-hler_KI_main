# CellCounter Pro — Codebase & Core Pipeline Architecture Survey Report

**Author:** teamwork_preview_explorer_survey_1  
**Timestamp:** 2026-08-31T23:05:40+02:00  
**Target:** Architecture & Core Image Processing Pipeline Survey  

---

## 1. Executive Summary

CellCounter Pro is a clean, modular, offline-first Python/Streamlit cell counting and viability analysis application designed for brightfield microscopy. The codebase strictly enforces separation of concerns:
- **`src/core/`**: Pure image processing algorithms (preprocessing, Watershed segmentation, viability classification, TIFF/metadata handling, statistical metrics). Free of UI logic.
- **`src/ui/`**: Streamlit-based web frontend (interactive dashboard, sidebar controls, preset selection, Plotly charts).
- **`src/utils/`**: Utilities for rotating file logging, SQLite storage, YAML preset management, and CSV/PNG export.
- **`tests/`**: Pytest suite containing 10 tests across 5 test modules using 4 synthetic test images.

All 10 tests currently pass (`pytest -v` passed in ~0.94s).

---

## 2. Directory Structure & File Inventory

```
antigravity/
├── config.yaml                     # Central YAML configuration & labor presets
├── requirements.txt                # Dependencies (opencv, numpy, streamlit, plotly, tifffile, pytest, etc.)
├── GEMINI.md                       # Project coding rules & constraints
├── README.md                       # Documentation & quickstart guide
├── data/
│   └── cell_counter.db             # SQLite database for analysis history and cell records
├── logs/
│   └── cell_counter.log            # Rotating application log file
├── src/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── preprocessing.py        # Grayscale conversion, downscaling, CLAHE, Gaussian denoise, flatfield
│   │   ├── segmentation.py         # Enhanced Peak Watershed segmentation, local maxima detection
│   │   ├── viability.py            # Trypan blue viability (I_core vs. I_ring local background subtraction)
│   │   ├── tiff_handler.py         # 16-Bit TIFF loader, percentile normalization, Z-stack projection
│   │   └── metrics.py              # Statistical metrics & summary distributions
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── app.py                  # Main Streamlit web application & tab workflow
│   │   ├── components.py           # Sidebar parameter controls, preset selector & preset saver
│   │   └── visualization.py        # Plotly charts (Viability Donut, Size Histogram, Scatter Plot)
│   └── utils/
│       ├── __init__.py
│       ├── config_manager.py       # YAML loader/saver and preset management
│       ├── database.py             # SQLite connection, schema init, analysis & cell record persistence
│       ├── io_export.py            # CSV data generator & high-resolution annotated overlay drawer
│       └── logger.py               # Rotating file handler & console logger setup
└── tests/
    ├── __init__.py
    ├── generate_test_images.py     # Generates 4 synthetic test images (clean cluster, vignetting, dust, 16-bit)
    ├── data/                       # Synthetic test images directory
    │   ├── synthetic_clean_cluster.png
    │   ├── synthetic_vignetting_gradient.png
    │   ├── synthetic_dust_artifacts.png
    │   └── synthetic_16bit_microscopy.tiff
    ├── test_preprocessing.py       # 4 unit tests for preprocessing operations
    ├── test_segmentation.py        # 2 unit tests for Watershed segmentation & cluster splitting
    ├── test_viability.py           # 1 unit test for Trypan blue viability classification
    ├── test_tiff.py                # 2 unit tests for 16-bit TIFF loading and normalization
    └── test_database.py            # 1 unit test for SQLite operations
```

---

## 3. Core Image Processing & Watershed Segmentation Pipeline

The core image processing workflow proceeds in 8 well-defined stages:

```
[Raw Image (PNG/JPEG/TIFF)]
         │
         ▼ (tiff_handler.load_image_with_metadata)
[8-bit Normalized Image + Metadata (µm/px)]
         │
         ▼ (preprocessing.to_grayscale)
[2D Grayscale Array (uint8)]
         │
         ▼ (preprocessing.downscale_image_if_needed)
[Working Resolution Image + Scale Factor]
         │
         ▼ (preprocessing.apply_clahe + denoise_image)
[Preprocessed Image (Enhanced Local Contrast & Denoised)]
         │
         ▼ (segmentation.segment_cells)
  ├─ 1. Adaptive Thresholding (Gaussian C) + Otsu AND combination
  ├─ 2. Morphological Close (3x3 ellipse) + Binary Hole Filling + Open
  ├─ 3. Sure Background: Dilation (5x5 ellipse)
  ├─ 4. Distance Transformation (cv2.DIST_L2, 5x5)
  ├─ 5. Local Peak Detection (find_local_peaks: dilation-based NMS)
  ├─ 6. Marker Filtering via connectedComponents (area >= min_marker_area_px)
  ├─ 7. Unknown boundary region calculation (sure_bg - filtered_seeds)
  ├─ 8. cv2.watershed execution
  └─ 9. Contour extraction, size/shape filtering (min/max diameter, circularity, solidity), rescaling
         │
         ▼ (viability.classify_viability)
[Viability Classification (I_core - I_ring <= threshold -> DEAD / LIVE)]
         │
         ▼ (metrics.compute_summary_statistics)
[Aggregated Statistical Metrics]
         │
         ▼ (io_export & visualization & database)
[Annotated Overlay Image, CSV Data, Plotly Charts, SQLite DB]
```

### Detailed Algorithm Steps in `src/core/`

#### 1. Image Loading & Normalization (`src/core/tiff_handler.py`)
- **TIFF Handling**: Inspects TIFF tags (`XResolution`, `ResolutionUnit` = 2 [inch] or 3 [cm]) to compute physical resolution `um_per_pixel`.
- **Multi-slice & Multi-channel**: Z-stacks are converted to 2D via Maximum Intensity Projection (`np.max(arr, axis=0)` or `np.max(arr, axis=(0, 1))`).
- **Percentile Normalization (`normalize_to_8bit`)**:
  - Calculates 1st (`p_low=1.0`) and 99th (`p_high=99.0`) percentiles.
  - Robustly clips outliers and scales pixel intensities to $[0, 255]$:
    $$\text{norm} = \left\lfloor \frac{\text{clip}(I, v_{\min}, v_{\max}) - v_{\min}}{v_{\max} - v_{\min}} \times 255 \right\rfloor$$

#### 2. Preprocessing & Downscaling (`src/core/preprocessing.py`)
- **Grayscale Conversion (`to_grayscale`)**: Converts RGBA/RGB/BGR to uint8 2D grayscale.
- **Dynamic Downscaling (`downscale_image_if_needed`)**:
  - If $\max(\text{height}, \text{width}) > \text{max\_dimension}$ (default 2048 px), downsamples using `cv2.INTER_AREA` with scale factor:
    $$s = \frac{\text{max\_dimension}}{\max(H, W)}$$
  - Scale factor $s \le 1.0$ is preserved so all coordinates, contours, and areas are scaled back to the original full-resolution space:
    $$(x_{\text{orig}}, y_{\text{orig}}) = \left(\frac{x_{\text{work}}}{s}, \frac{y_{\text{work}}}{s}\right), \quad \text{Area}_{\text{orig}} = \frac{\text{Area}_{\text{work}}}{s^2}$$
- **CLAHE (`apply_clahe`)**: Enhances local cellular contrast with clip limit (default 2.0) and grid size (8x8).
- **Denoising (`denoise_image`)**: Gaussian blur with odd kernel size (default 5).
- **Flatfield Correction (`remove_background_flatfield`)**: Morphological dilation using an elliptical kernel followed by subtraction of the grayscale image from background.

#### 3. Enhanced Peak Watershed Segmentation (`src/core/segmentation.py`)
- **Dual Thresholding**:
  - `cv2.adaptiveThreshold` (Gaussian C, inverse binary, `block_size=21`, `C=5`).
  - `cv2.threshold` with Otsu thresholding.
  - Combined via bitwise AND (`cv2.bitwise_and(binary_inv, otsu_inv)`).
  - Safety check: If combined foreground count $< 10\%$ of adaptive threshold, falls back to adaptive threshold.
- **Morphology & Hole-Filling (`fill_binary_holes`)**:
  - Morphological close with 3x3 ellipse.
  - All inner holes are filled via hierarchical contour drawing (`cv2.RETR_CCOMP`).
  - Morphological open with 3x3 ellipse to remove single-pixel specks.
- **Distance Transform**:
  - Euclidean distance transformation: `cv2.distanceTransform(opening, cv2.DIST_L2, 5)`.
- **Local Peak Detection (`find_local_peaks`)**:
  - Peak neighborhood window size: $k_{\text{peak}} = \max(3, \lfloor 0.6 \times d_{\text{min,work}} \rceil)$.
  - Dilates distance map with ones kernel $(k_{\text{peak}} \times k_{\text{peak}})$.
  - Peaks identified where $D = \text{dilate}(D)$ AND $D \ge \text{ratio} \times \max(D)$ AND $D > 1.0$.
- **Marker Seed Filtering**:
  - Connected components with stats (`cv2.connectedComponentsWithStats`).
  - Rejects seed regions with area $< \text{min\_marker\_area\_px}$.
  - Fallback: If no valid markers remain, applies global threshold at $0.25 \times \max(D)$.
- **Watershed Seeding**:
  - Foreground seeds labeled $2, 3, \dots, N+1$.
  - Sure background labeled $1$.
  - Unknown transition zone ($\text{sure\_bg} \setminus \text{seeds}$) labeled $0$.
  - `cv2.watershed(color_img, markers)` assigns boundaries as $-1$.
- **Cell Extraction & Shape Filtering**:
  - For each label $> 1$:
    - Extracts contour via `cv2.findContours(cell_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)`.
    - Area check: $\text{Area}_{\text{min,work}} \le \text{Area} \le \text{Area}_{\text{max,work}}$.
    - Circularity check:
      $$\text{Circularity} = \frac{4 \pi \cdot \text{Area}}{\text{Perimeter}^2} \ge \text{min\_circularity} \quad (\text{default } 0.20 \text{ in code / } 0.35 \text{ in config})$$
    - Solidity check:
      $$\text{Solidity} = \frac{\text{Area}}{\text{ConvexHullArea}} \ge \text{min\_solidity} \quad (\text{default } 0.35 \text{ in code / } 0.50 \text{ in config})$$
    - Centroid calculated from moments $(m_{10}/m_{00}, m_{01}/m_{00})$.
    - Coordinates and contours transformed back to original resolution.

#### 4. Viability Classification (`src/core/viability.py`)
- **Principle**: Local background subtraction around each segmented cell.
  - Inner Core Mask: $\text{Core} = \text{erode}(\text{CellMask}, 3\times 3)$.
  - Outer Ring Mask: $\text{Ring} = \text{dilate}(\text{CellMask}, (2w+1)\times(2w+1)) \setminus \text{CellMask}$ where $w = \text{ring\_width\_px}$.
  - Mean Intensities: $I_{\text{core}} = \text{mean}(I_{\text{gray}}, \text{Core})$, $I_{\text{ring}} = \text{mean}(I_{\text{gray}}, \text{Ring})$.
  - $\Delta I = I_{\text{core}} - I_{\text{ring}}$.
  - Classification: If $\Delta I \le \text{intensity\_diff\_threshold}$ (e.g. $-12.0$), cell is marked `"DEAD"` (Trypan blue uptake absorbs light, causing core to be darker than ring); otherwise `"LIVE"`.

---

## 4. Parameter Reference Across Presets

The application manages presets via `config.yaml`:

| Parameter | Key in YAML | `Standard_Brightfield` | `Trypan_Blue_Viability` | `High_Density_Yeast` | Description |
|---|---|---|---|---|---|
| **Max Dimension** | `preprocessing.max_dimension` | 2048 | 2048 | 2560 | Image downscaling limit |
| **CLAHE Clip Limit** | `preprocessing.clahe_clip_limit` | 2.0 | 2.5 | 3.0 | Local contrast amplification limit |
| **CLAHE Grid Size** | `preprocessing.clahe_tile_grid_size` | [8, 8] | [8, 8] | [4, 4] | Tile dimensions for CLAHE |
| **Gaussian Kernel** | `preprocessing.gaussian_blur_kernel` | 5 | 5 | 3 | Denoising filter size |
| **Min Cell Diameter** | `segmentation.min_cell_diameter_px` | 15 | 12 | 6 | Minimum expected cell diameter |
| **Max Cell Diameter** | `segmentation.max_cell_diameter_px` | 120 | 100 | 40 | Maximum expected cell diameter |
| **Adaptive Block Size** | `segmentation.adaptive_thresh_block_size` | 21 | 25 | 15 | Window size for adaptive thresholding |
| **Adaptive Constant C** | `segmentation.adaptive_thresh_c` | 5 | 4 | 3 | Subtracted constant from local mean |
| **Min Marker Area** | `segmentation.min_marker_area_px` | 3 | 4 | 2 | Minimum peak seed size |
| **Distance Ratio** | `segmentation.dist_threshold_ratio` | 0.25 | 0.30 | 0.40 | Relative distance peak threshold ($\text{ratio} \times D_{\max}$) |
| **Min Circularity** | `segmentation.min_circularity` | 0.35 | 0.30 | 0.40 | Shape roundness cutoff ($4\pi A / P^2$) |
| **Min Solidity** | `segmentation.min_solidity` | 0.50 | 0.45 | 0.60 | Ratio of cell area to convex hull area |
| **Viability Enabled** | `viability.enabled` | true | true | false | Enables Trypan blue live/dead analysis |
| **Ring Width** | `viability.ring_width_px` | 4 | 5 | 3 | Annulus thickness around cell |
| **Intensity Diff Thresh**| `viability.intensity_diff_threshold`| -12.0 | -15.0 | -10.0 | $I_{\text{core}} - I_{\text{ring}}$ dead cell cutoff |

---

## 5. Logging Setup & Configuration Management

### Logging (`src/utils/logger.py`)
- **Logger Name**: `"cell_counter"` (child loggers via `get_logger(module_name)`: e.g., `"cell_counter.segmentation"`).
- **Handlers**:
  - `StreamHandler` (stdout/stderr console).
  - `RotatingFileHandler` writing to `logs/cell_counter.log` (UTF-8).
- **Rotation Configuration**:
  - `max_bytes`: 5,242,880 bytes (5 MB).
  - `backup_count`: 3 backup log files.
- **Log Format**: `%(asctime)s - %(name)s - %(levelname)s - %(message)s` (`YYYY-MM-DD HH:MM:SS`).
- **UI Integration**: `src/ui/app.py` Tab 3 ("🛠️ System & Support-Logs") includes an interactive log preview expander and a download button to export `cell_counter.log` directly.

### Configuration Management (`src/utils/config_manager.py`)
- **File**: `config.yaml` located at root.
- **API Functions**:
  - `load_config(path)`: Safe YAML loading with UTF-8 encoding.
  - `save_config(data, path)`: Persists YAML with `allow_unicode=True`.
  - `get_available_presets(config_data)`: Returns list of preset names.
  - `get_preset(preset_name, config_data)`: Retrieves dictionary for a specific preset with fallback to the first preset if not found.
  - `save_preset(preset_name, preset_data, path)`: Adds or updates a preset and saves `config.yaml`.

### Database Architecture (`src/utils/database.py`)
- **Engine**: SQLite3, file at `data/cell_counter.db`.
- **Thread Safety**: `check_same_thread=False` configured for multi-threaded Streamlit runtime. Foreign keys enabled via `PRAGMA foreign_keys = ON;`.
- **Schema**:
  - **`analyses` table**:
    - `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
    - `timestamp` (DATETIME DEFAULT CURRENT_TIMESTAMP)
    - `filename` (TEXT)
    - `total_cells` (INTEGER)
    - `live_cells` (INTEGER)
    - `dead_cells` (INTEGER)
    - `viability_pct` (REAL)
    - `preset_name` (TEXT)
  - **`cells` table**:
    - `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
    - `analysis_id` (INTEGER, FOREIGN KEY -> `analyses.id` ON DELETE CASCADE)
    - `cell_id` (INTEGER)
    - `x_px`, `y_px`, `area_px`, `area_um2`, `circularity`, `intensity_diff`, `status`

---

## 6. End-to-End Data Flow Mapping

```
[Raw User Input: Gallery Sample or File Uploader]
                    │
                    ▼
[file_bytes, filename]
                    │
                    ▼  load_image_with_metadata(file_bytes, filename)
[img_raw: np.ndarray, metadata: dict (um_per_pixel, is_tiff, dtype)]
                    │
                    ▼  to_grayscale(img_raw)
[gray_orig: 2D uint8]
                    │
                    ▼  downscale_image_if_needed(gray_orig, max_dimension)
[gray_work: 2D uint8, scale_factor: float]
                    │
                    ▼  apply_clahe(gray_work) -> denoise_image(clahe)
[denoised: 2D uint8]
                    │
                    ▼  segment_cells(denoised, seg_params, scale_factor, um_per_px)
[cell_list: list[dict], markers: np.ndarray (int32), binary: np.ndarray (uint8)]
  Each cell dict:
  {
    "cell_id": int,
    "label": int,
    "x_px": float, "y_px": float,         # Original full-resolution coords
    "x_work": float, "y_work": float,     # Working resolution coords
    "area_px": float, "area_um2": float,  # Scaled areas
    "circularity": float, "solidity": float,
    "contour_orig": np.ndarray,           # Contour in original image space
    "contour_work": np.ndarray,           # Contour in working image space
    "mask_work": np.ndarray               # Single-cell binary mask
  }
                    │
                    ▼  classify_viability(denoised, cell_list, viab_params)
[cell_list enriched with: "status" ('LIVE'/'DEAD'), "i_core", "i_ring", "intensity_diff",
 viab_summary: dict ("total_cells", "live_cells", "dead_cells", "viability_pct")]
                    │
                    ▼  compute_summary_statistics(cell_list, viab_summary)
[summary: dict ("total_cells", "live_cells", "dead_cells", "viability_pct",
                "mean_area_px", "std_area_px", "min_area_px", "max_area_px",
                "mean_circularity", "mean_area_um2")]
                    │
   ┌────────────────┼────────────────┬────────────────┬────────────────┐
   ▼                ▼                ▼                ▼                ▼
[create_annotated_overlay]  [generate_csv_data]  [Plotly Charts]  [SQLite DB]   [Streamlit UI]
Annotated BGR image with    CSV formatted string  Donut, size      save_analysis_ Display metrics,
contours, centers, IDs      for download          hist, scatter    result()       dual panel, tabs
```

---

## 7. Analysis of Requirements & Extension Touchpoints

### R1. Automatic Image Calibration
- **Goal**: Analyze raw/grayscale images statistically (histogram distribution, local contrast, brightness gradient) to compute optimal Watershed parameters (`adaptive_thresh_c`, `clahe_clip_limit`, `min_marker_area_px`, `dist_threshold_ratio`) automatically.
- **Touchpoint**: 
  - Pure core algorithm should be added to `src/core/` (e.g. `src/core/calibration.py` or within `preprocessing.py`).
  - Must log calibration parameters at `INFO` level.
  - UI sidebar in `src/ui/components.py` maintains manual sliders as overrides.
  - Acceptance criterion: On 3 test images from `tests/data/`, auto-calibration detects at least as many cells as the fixed configuration without manual intervention.

### R2. Confidence Traffic Light System (Green / Yellow / Red)
- **Goal**: Assign a confidence score $C \in [0.0, 1.0]$ to each segmented cell based on circularity, solidity, and local Contrast-to-Noise Ratio (CNR).
- **Traffic Light Categories**:
  - Green (confident): $C \ge 0.7$
  - Yellow (uncertain): $0.4 \le C < 0.7$
  - Red (likely false): $C < 0.4$
- **Touchpoints**:
  - Compute confidence score per cell in `src/core/metrics.py` or `src/core/segmentation.py`.
  - Update `src/utils/io_export.py` (`create_annotated_overlay` with Green/Yellow/Red colors, `generate_csv_data` adding `confidence` column).
  - Update `src/ui/app.py` metric row to display "Unsichere Zellen: X" and "Problematische Regionen: Y".

### R3. Manual Correction UI
- **Goal**: Provide a lightweight manual correction section beneath the dual-panel in `src/ui/app.py`.
- **UI Elements**:
  - Number input `'Korrigierte Gesamtzahl'` pre-filled with the algorithm count.
  - Button `'Korrektur speichern'` saving JSON to `data/corrections/<timestamp>_<filename>.json`.
  - JSON Schema: `{"original_count": int, "corrected_count": int, "delta": int, "markers": list, "image_path": str}`.

### Code Quality & Minor Observations
1. In `src/utils/io_export.py` line 114: `math.sqrt` is referenced in the fallback circle branch, but `import math` was omitted at the top of `src/utils/io_export.py`.
2. All 10 existing unit tests pass cleanly in pytest.

---

## 8. Verification Strategy

1. **Test Execution**: Run `.venv\Scripts\python -m pytest -v` to ensure 100% test pass rate across existing test suites.
2. **Preset Verification**: Verify that `Standard_Brightfield`, `Trypan_Blue_Viability`, and `High_Density_Yeast` presets load correctly and contain consistent parameter types.
3. **Pipeline Completeness**: Confirm that all outputs of `segment_cells` flow seamlessly into `classify_viability`, `compute_summary_statistics`, `create_annotated_overlay`, and `save_analysis_result`.
