# Project: CellCounter Pro Enhancements

## Architecture

CellCounter Pro is a Python/Streamlit cell counting and viability analysis desktop/web application for brightfield microscopy. The architecture follows a strict 3-tier separation of concerns:

- **`src/core/` (Pure Algorithms)**:
  - `calibration.py` (New): Statistical image analysis (histogram, noise, illumination gradient) and automatic Watershed parameter calibration.
  - `confidence.py` (New): Multi-factor cell confidence scoring (circularity, solidity, local CNR) and traffic-light categorization (Green/Yellow/Red).
  - `preprocessing.py`: Grayscale conversion, downscaling, CLAHE contrast enhancement, Gaussian denoising, flatfield correction.
  - `segmentation.py`: Adaptive + Otsu dual thresholding, hole filling, Euclidean distance transform, peak seed detection, Watershed segmentation, contour extraction.
  - `viability.py`: Trypan blue live/dead classification using local annulus background subtraction.
  - `metrics.py`: Cytometric distribution statistics, size metrics, viability summary, and confidence metrics aggregation.
  - `tiff_handler.py`: 16-bit microscopy TIFF loader, percentile normalization, multi-slice Z-stack projection.

- **`src/utils/` (Storage, I/O, Logging)**:
  - `io_export.py`: Annotated overlay generation with confidence color coding, CSV report generator with confidence column, and manual correction JSON persistence.
  - `database.py`: SQLite connection, schema definition, and analysis history persistence.
  - `config_manager.py`: YAML configuration and preset loading/saving.
  - `logger.py`: Rotating file handler and console logger.

- **`src/ui/` (Streamlit Frontend)**:
  - `app.py`: Main dashboard, dual-panel image comparison, metric cards (total, viability, uncertain cells, problematic regions), manual correction UI, chart visualizations, export buttons.
  - `components.py`: Sidebar controls, preset selector, auto-calibration toggle, and slider overrides.
  - `visualization.py`: Plotly charts (viability donut, size histogram, spatial cytogram).

- **`tests/` (Pytest Suite)**:
  - `test_preprocessing.py`, `test_segmentation.py`, `test_viability.py`, `test_tiff.py`, `test_database.py` (10 existing tests).
  - `test_calibration.py` (New): Auto-calibration statistical tests, parameter bounds, cell count baseline verification ($\ge 7$ cells on 3 test images), and INFO-level logging.
  - `test_confidence.py` (New): Confidence score normalization, geometric/contrast penalties, traffic light categories, summary metrics, and CSV column.
  - `test_corrections.py` (New): Manual correction JSON saving, directory auto-creation, and schema validation.

---

## Feature Inventory

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Statistical Image Analysis | Compute histogram entropy, dynamic range, Laplacian noise energy, and radial illumination gradient from 2D grayscale image | M1 | ORIGINAL_REQUEST §R1 |
| 2 | Auto Parameter Calibration | Automatically adjust CLAHE clip limit, adaptive threshold block size & C, min marker area, and distance transform ratio based on image stats; log at INFO level | M1 | ORIGINAL_REQUEST §R1 |
| 3 | Confidence Scoring Algorithm | Calculate normalized confidence score $S_{\text{conf}} \in [0, 1]$ per cell from circularity, solidity, and local CNR | M2 | ORIGINAL_REQUEST §R2 |
| 4 | Traffic Light Color Categorization | Map confidence scores to Green ($\ge 0.70$), Yellow ($0.40\text{--}0.70$), and Red ($< 0.40$) | M2 | ORIGINAL_REQUEST §R2 |
| 5 | Traffic Light Annotated Overlay | Draw cell contours and centroid markers in high-resolution overlay image with Green/Yellow/Red colors | M2 | ORIGINAL_REQUEST §R2 |
| 6 | Confidence Aggregation in Metrics | Summarize cell counts for `uncertain_cells` (Yellow) and `problematic_cells` (Red) in summary statistics | M2 | ORIGINAL_REQUEST §R2 |
| 7 | CSV Export with Confidence Column | Include `'Confidence'` column in exported CSV data alongside cell coordinates, area, and viability | M2 | ORIGINAL_REQUEST §R2 |
| 8 | Manual Correction JSON Persistence | Save `{original_count, corrected_count, delta, markers, image_path, timestamp}` to `data/corrections/<timestamp>_<filename>.json` | M3 | ORIGINAL_REQUEST §R3 |
| 9 | Streamlit Auto-Calibration UI & Slider Override | Sidebar toggle for auto-calibration, initialize sliders from calibrated values, preserve manual overrides | M4 | ORIGINAL_REQUEST §R1 |
| 10 | Streamlit Metric Cards for Confidence | Prominently display "Unsichere Zellen: X" and "Problematische Regionen: Y" in the main results view | M4 | ORIGINAL_REQUEST §R2 |
| 11 | Streamlit Manual Correction UI Section | Rapid correction input placed directly below Dual-Panel image view with number input and "Korrektur speichern" button | M4 | ORIGINAL_REQUEST §R3 |
| 12 | Regression & Acceptance Test Verification | Ensure all 10 existing tests pass + new unit tests pass + auto-calibration yields $\ge$ baseline count on 3 test images | M4 | ORIGINAL_REQUEST §Acceptance |

---

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Core Auto-Calibration Engine | Implement `src/core/calibration.py` with image statistical analysis, parameter auto-tuning, INFO logging, and `tests/test_calibration.py`. | None | PLANNED |
| M2 | Confidence Scoring, Metrics & Overlay/CSV | Implement `src/core/confidence.py`, update `src/core/metrics.py`, `src/core/segmentation.py`, and `src/utils/io_export.py` (overlay + CSV), and `tests/test_confidence.py`. | M1 | PLANNED |
| M3 | Manual Correction Persistence Subsystem | Implement `save_manual_correction` in `src/utils/io_export.py` (saving to `data/corrections/`), and `tests/test_corrections.py`. | None | PLANNED |
| M4 | Streamlit UI Integration & Acceptance Verification | Integrate auto-calibration toggle/overrides in `src/ui/components.py`, confidence metric cards and manual correction UI in `src/ui/app.py`, run full pytest suite and verify acceptance criteria. | M1, M2, M3 | PLANNED |

---

## Interface Contracts

### 1. Auto-Calibration (`src/core/calibration.py`)
```python
def analyze_image_statistics(gray: np.ndarray) -> Dict[str, float]:
    """Computes statistical metrics (mean, std, dynamic_range, laplacian_var, radial_gradient, etc.)."""

def auto_calibrate_parameters(
    gray: np.ndarray,
    base_params: Optional[Dict[str, Any]] = None
) -> Tuple[Dict[str, Any], Dict[str, float]]:
    """Calibrates Watershed parameters based on image statistics and emits INFO-level logs.
    
    Returns:
        calibrated_params: Dict containing:
            - 'clahe_clip_limit': float (e.g. 1.5 - 3.5)
            - 'adaptive_thresh_block_size': int (odd, e.g. 15 - 31)
            - 'adaptive_thresh_c': int (e.g. 3 - 6)
            - 'min_marker_area_px': int (e.g. 2 - 6)
            - 'dist_threshold_ratio': float (e.g. 0.18 - 0.35)
        image_stats: Dict of measured statistics.
    """
```

### 2. Confidence Scoring (`src/core/confidence.py`)
```python
def compute_cell_confidence(
    cell: Dict[str, Any],
    gray_work: np.ndarray,
    weights: Optional[Tuple[float, float, float]] = (0.35, 0.35, 0.30)
) -> Dict[str, Any]:
    """Enriches cell dictionary with:
        - 'confidence': float in [0.0, 1.0] (rounded to 3 decimals)
        - 'confidence_category': 'GREEN' | 'YELLOW' | 'RED'
        - 'cnr': float
    """

def get_confidence_category(confidence: float) -> str:
    """Returns 'GREEN' (>=0.70), 'YELLOW' (0.40 <= c < 0.70), or 'RED' (<0.40)."""
```

### 3. Summary Metrics (`src/core/metrics.py`)
```python
def compute_summary_statistics(
    cell_list: List[Dict[str, Any]],
    viability_summary: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Returns summary dictionary enriched with:
        - 'uncertain_cells': int (Yellow cells, 0.40 <= score < 0.70)
        - 'problematic_cells': int (Red cells, score < 0.40)
        - 'high_confidence_cells': int (Green cells, score >= 0.70)
        - 'mean_confidence': float
    """
```

### 4. Overlay & CSV Export (`src/utils/io_export.py`)
```python
def create_annotated_overlay(
    image: np.ndarray,
    cell_list: List[Dict[str, Any]],
    show_labels: bool = True,
    scale_factor: float = 1.0
) -> np.ndarray:
    """Draws traffic light contours & centroids:
        - GREEN: (0, 220, 0)
        - YELLOW: (0, 215, 255)
        - RED: (0, 0, 235)
    """

def generate_csv_data(cell_list: List[Dict[str, Any]]) -> str:
    """Generates semicolon-separated CSV string with 'Confidence' and 'Confidence_Category'."""
```

### 5. Manual Correction Persistence (`src/utils/io_export.py`)
```python
def save_manual_correction(
    filename: str,
    original_count: int,
    corrected_count: int,
    cell_list: List[Dict[str, Any]],
    image_path: str = "",
    output_dir: str = "data/corrections"
) -> str:
    """Saves correction record to data/corrections/<timestamp>_<filename>.json.
    
    Returns:
        Absolute or relative path to saved JSON file.
    """
```

---

## Code Layout

- `src/core/`
  - `calibration.py`: Implementation of R1 auto-calibration logic.
  - `confidence.py`: Implementation of R2 confidence score logic.
  - `metrics.py`: Confidence metrics aggregation.
  - `segmentation.py`: Enrichment of cell list with confidence scores.
  - `preprocessing.py`: Image preprocessing helpers.
  - `viability.py`: Viability classification.
  - `tiff_handler.py`: TIFF handling.
  - `__init__.py`: Public core API exports.
- `src/utils/`
  - `io_export.py`: Overlay drawing (R2), CSV export (R2), Manual correction JSON persistence (R3).
  - `database.py`: SQLite persistence.
  - `logger.py`: Logging.
  - `config_manager.py`: Config management.
- `src/ui/`
  - `components.py`: Sidebar controls and auto-calibration toggle/slider defaults (R1).
  - `app.py`: Metric cards (R2), Manual correction UI (R3), auto-calibration integration (R1).
- `tests/`
  - `test_calibration.py`: Unit tests for R1 calibration.
  - `test_confidence.py`: Unit tests for R2 confidence and metrics.
  - `test_corrections.py`: Unit tests for R3 manual correction persistence.
  - `test_preprocessing.py`, `test_segmentation.py`, `test_viability.py`, `test_tiff.py`, `test_database.py`: Existing tests.
