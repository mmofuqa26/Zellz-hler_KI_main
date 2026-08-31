# Feature & Architecture Survey Report: CellCounter Pro Extensions (R1, R2, R3)

**Author:** teamwork_preview_explorer_survey_2  
**Date:** 2026-08-31  
**Project:** CellCounter Pro (Automated Microscopy Cell Counter)  
**Target Workspace:** `c:\Users\miran\Documents\Zellzählerki\antigravity`  
**Guidelines Reference:** `GEMINI.md`, `ORIGINAL_REQUEST.md`

---

## Executive Summary

This survey analyzes the architecture, module boundaries, mathematical foundations, and UI integration pathways for the three required extensions:
1. **R1: Automatic Parameter Calibration per Image** (Histogram, contrast, illumination gradient analysis, parameter adaptation, INFO logging, slider override preservation).
2. **R2: Confidence Score per Cell & Traffic Light Overlay** (Circularity, solidity, local CNR, Green/Yellow/Red visual coding, metric cards "Unsichere Zellen" / "Problematische Regionen", CSV confidence column).
3. **R3: Manual Correction UI & JSON Persistence** (Below dual-panel, prefilled number input, delta tracking, JSON persistence to `data/corrections/<timestamp>_<filename>.json`).

All design specifications strictly follow the architectural boundaries set forth in `GEMINI.md`:
- **Core (`src/core/`)**: All image processing, statistical calibration, segmentation, confidence calculation, and summary metrics.
- **UI (`src/ui/`)**: Streamlit rendering, session state management, input handling, Plotly charts; *no business logic*.
- **Utils (`src/utils/`)**: Database, JSON/CSV I/O, file persistence, logging, configuration management.

---

## 1. Requirement 1 (R1): Automatic Parameter Calibration per Image

### 1.1 Problem & Objective
Microscopy images exhibit wide variance in lighting, contrast, vignetting, and noise (e.g. clean clusters vs. dust artifacts vs. vignetting gradient). Currently, parameters are fixed in presets (`config.yaml`). The goal of R1 is to analyze the image prior to segmentation and automatically calibrate the parameters:
- CLAHE Clip Limit (`clahe_clip_limit`)
- Adaptive Threshold Block Size (`adaptive_thresh_block_size`) & Constant C (`adaptive_thresh_c`)
- Minimum Marker Area (`min_marker_area_px`)
- Distance Transform Threshold Ratio (`dist_threshold_ratio`)

### 1.2 Statistical Image Analysis & Mathematical Formulation

The calibration function analyzes the 2D grayscale image (after downscaling if applicable) across three core dimensions:

#### 1. Histogram Distribution & Dynamic Range
- **Mean & Standard Deviation:** $\mu = \frac{1}{N}\sum I(x,y)$, $\sigma = \sqrt{\frac{1}{N}\sum (I(x,y) - \mu)^2}$
- **Percentiles (Dynamic Range):** $P_5$ and $P_{95}$. Dynamic range $\Delta P = P_{95} - P_5$.
- **Histogram Entropy:** $H = -\sum_{k=0}^{255} p_k \log_2(p_k + \epsilon)$
- **Interpretation:**
  - $\Delta P < 60$ or low $\sigma$: Low-contrast/hazy image $\to$ increase `clahe_clip_limit` (e.g., 2.5 - 3.5).
  - Skewed mean ($\mu < 80$ or $\mu > 200$): Under- or over-exposed image $\to$ adjust adaptive threshold constant $C$.

#### 2. Local Contrast & High-Frequency Texture (Noise/Dust vs. Clean)
- **Laplacian Variance:** $V_{\text{Lap}} = \operatorname{Var}(\nabla^2 I)$
- **High-Frequency Noise Index:** Measure of local gradient energy using Sobel or Scharr operators:
  $E_{\text{HF}} = \frac{1}{N}\sum \sqrt{G_x^2 + G_y^2}$
- **Interpretation:**
  - High $E_{\text{HF}}$ with small isolated peaks (dust/artifacts): Increase `min_marker_area_px` (from 2-3 to 4-6) to prevent false-positive peak detection on noise grains.
  - Low $E_{\text{HF}}$: Clean image, allow smaller marker area (`min_marker_area_px = 2` or `3`).

#### 3. Illumination Gradient & Non-Uniformity (Vignetting / Background Inhomogeneity)
- **Spatial Quadrant / Radial Analysis:** Divide image into center ($I_{\text{center}}$) and 4 corners ($I_{\text{corners}}$).
  $\text{Gradient}_{\text{radial}} = \frac{|\bar{I}_{\text{center}} - \bar{I}_{\text{corners}}|}{\bar{I}_{\text{center}} + \epsilon}$
- **Low-pass Background Profile:** Estimate low-frequency background via large Gaussian blur or morphological opening.
- **Interpretation:**
  - High $\text{Gradient}_{\text{radial}} > 0.15$ (strong vignetting/shading): Smaller `adaptive_thresh_block_size` (e.g. 15–21 instead of 31+) is critical so local threshold adapts rapidly across the shading field; also ensure `dist_threshold_ratio` is tuned (e.g., 0.20–0.25).

### 1.3 Parameter Mapping Table

| Metric Observed | Condition | Calibrated Parameter Adjustment |
|---|---|---|
| Dynamic Range $\Delta P$ | $\Delta P < 80$ (Low Contrast) | `clahe_clip_limit`: $2.8 - 3.5$ (Enhance local edges) |
| Dynamic Range $\Delta P$ | $\Delta P \ge 80$ (Good Contrast) | `clahe_clip_limit`: $1.8 - 2.2$ (Standard) |
| Illumination Gradient | $\text{Gradient}_{\text{radial}} \ge 0.15$ (Vignetting) | `adaptive_thresh_block_size`: 17 – 23, `adaptive_thresh_c`: 4 – 5 |
| Illumination Gradient | $\text{Gradient}_{\text{radial}} < 0.15$ (Uniform) | `adaptive_thresh_block_size`: 21 – 27, `adaptive_thresh_c`: 4 – 6 |
| Noise / Dust Index | High $E_{\text{HF}}$ or isolated tiny spots | `min_marker_area_px`: 4 – 6, `dist_threshold_ratio`: 0.25 – 0.30 |
| Noise / Dust Index | Low noise, high density clusters | `min_marker_area_px`: 2 – 3, `dist_threshold_ratio`: 0.18 – 0.22 |

### 1.4 Architectural Placement (Core Layer)
- **Location:** `src/core/preprocessing.py` (or a dedicated `src/core/calibration.py`).
- **Function Signature:**
  ```python
  def auto_calibrate_parameters(
      gray: np.ndarray,
      base_params: Dict[str, Any] = None,
  ) -> Tuple[Dict[str, Any], Dict[str, float]]:
      """Analysiert Bildstatistiken und berechnet optimal angepasste Segmentierungs-Parameter.
      
      Args:
          gray: 2D-Graustufenbild (uint8).
          base_params: Optionale Basis-Parameter aus dem aktiven Preset.
          
      Returns:
          Tuple[Dict[str, Any], Dict[str, float]]:
              - Wörterbuch mit kalibrierten Parametern (clahe_clip_limit, block_size, param_c, min_marker_area, dist_ratio).
              - Wörterbuch mit gemessenen Bildstatistiken (mean, std, contrast, gradient, noise_level).
      """
  ```
- **Logging Requirement:**
  ```python
  logger.info(
      f"Auto-Kalibrierung: CLAHE={calibrated['clahe_clip_limit']:.2f}, "
      f"BlockSize={calibrated['adaptive_thresh_block_size']}, "
      f"ParamC={calibrated['adaptive_thresh_c']}, "
      f"MinMarkerArea={calibrated['min_marker_area_px']}, "
      f"DistRatio={calibrated['dist_threshold_ratio']:.2f} "
      f"(Stats: Kontrast={stats['contrast']:.1f}, Gradient={stats['gradient']:.2f}, Rauschen={stats['noise']:.1f})"
  )
  ```

### 1.5 UI Integration & Slider Override Preservation
To ensure that users can see the auto-calibrated values and still manually override them in the sidebar without the UI constantly overwriting user changes on Streamlit reruns:
1. **Session State Key Tracking:** In `st.session_state`:
   - Store `current_image_hash` or `current_filename`.
   - When a new image is loaded, trigger auto-calibration, store `calibrated_params` in `st.session_state`, and initialize/update the sidebar slider session state keys.
   - An "Auto-Kalibrierung" toggle (default: `True`) in the sidebar allows users to lock in calibrated settings or revert to manual preset defaults.
   - When the user drags a slider, the modified value is passed to `segment_cells(...)`, preserving the override.

---

## 2. Requirement 2 (R2): Confidence Score per Cell & Traffic Light Overlay

### 2.1 Problem & Objective
In automated segmentation, some detected regions are unambiguous single cells, while others may be dust artifacts, overlapping cell borders, or faint debris. R2 assigns each cell a normalized **Confidence Score** $S_{\text{conf}} \in [0.0, 1.0]$ based on three biological and geometric criteria:
1. **Circularity ($C$)**
2. **Solidity ($S$)**
3. **Local Contrast-to-Noise Ratio ($\text{CNR}$)**

Cells are categorized into a 3-tier traffic light system:
- 🟢 **Sicher / High Confidence (Green):** $S_{\text{conf}} \ge 0.70$
- 🟡 **Unsicher / Medium Confidence (Yellow):** $0.40 \le S_{\text{conf}} < 0.70$
- 🔴 **Problematisch / Low Confidence (Red):** $S_{\text{conf}} < 0.40$

### 2.2 Mathematical Definition of the Confidence Score

#### 1. Circularity ($C$)
$C = \frac{4 \pi \cdot \text{Area}}{\text{Perimeter}^2}$  
Normalized to $[0.0, 1.0]$. Circularity near $1.0$ indicates regular spherical cells; low circularity indicates irregular debris or elongated clumps.

#### 2. Solidity ($S$)
$S = \frac{\text{Area}}{\text{ConvexHullArea}}$  
Normalized to $[0.0, 1.0]$. Measures convexity. Deep indentations or branching artifacts yield low solidity.

#### 3. Local Contrast-to-Noise Ratio ($\text{CNR}$)
For each cell $i$, compute:
- Mean intensity inside cell core/mask: $\mu_{\text{core}}$
- Mean intensity in the local background ring surrounding the cell: $\mu_{\text{ring}}$
- Standard deviation of intensity in the background ring: $\sigma_{\text{ring}}$
- Raw CNR:
  $$\text{CNR}_{\text{raw}} = \frac{|\mu_{\text{core}} - \mu_{\text{ring}}|}{\sigma_{\text{ring}} + \epsilon} \quad (\epsilon = 1.0)$$
- Normalized CNR Score $S_{\text{CNR}} \in [0.0, 1.0]$:
  $$S_{\text{CNR}} = 1.0 - \exp\left(-\frac{\text{CNR}_{\text{raw}}}{k_{\text{cnr}}}\right) \quad (\text{with reference constant } k_{\text{cnr}} \approx 3.5)$$
  Or piecewise linear clamping: $S_{\text{CNR}} = \min\left(1.0, \frac{\text{CNR}_{\text{raw}}}{5.0}\right)$.

#### 4. Composite Confidence Score
$$S_{\text{conf}} = w_C \cdot C + w_S \cdot S + w_{\text{CNR}} \cdot S_{\text{CNR}}$$
Recommended weights:
- $w_C = 0.35$ (Circularity weight)
- $w_S = 0.35$ (Solidity weight)
- $w_{\text{CNR}} = 0.30$ (Local CNR weight)
- $w_C + w_S + w_{\text{CNR}} = 1.0$

Final score clamped: $S_{\text{conf}} = \max(0.0, \min(1.0, \text{round}(S_{\text{conf}}, 3)))$.

### 2.3 Architectural Mapping (Core & Utils)

1. **Score Calculation in Core (`src/core/metrics.py` or `src/core/segmentation.py`):**
   - Implemented as a standalone helper `compute_cell_confidence(cell: Dict[str, Any], gray_work: np.ndarray) -> float` or integrated into `classify_viability` / `segment_cells`.
   - Each cell dict in `cell_list` receives:
     - `cell["confidence"] = 0.85`
     - `cell["confidence_class"] = "HIGH" | "MEDIUM" | "LOW"` (or `"GREEN" | "YELLOW" | "RED"`)
     - `cell["cnr"] = 4.2`

2. **Summary Metrics in `src/core/metrics.py` (`compute_summary_statistics`):**
   - Compute counts:
     - `uncertain_cells`: Count of cells with $0.40 \le S_{\text{conf}} < 0.70$ (Yellow).
     - `problematic_cells`: Count of cells with $S_{\text{conf}} < 0.40$ (Red).
     - `high_confidence_cells`: Count of cells with $S_{\text{conf}} \ge 0.70$ (Green).
     - `mean_confidence`: Average confidence across all detected cells.

3. **Overlay Visualization in `src/utils/io_export.py` (`create_annotated_overlay`):**
   - Three-color palette (BGR):
     - `COLOR_HIGH = (0, 220, 0)` (Green: Sicher $\ge 0.7$)
     - `COLOR_MEDIUM = (0, 215, 255)` (Yellow: Unsicher $0.4 - 0.7$)
     - `COLOR_LOW = (0, 0, 235)` (Red: Problematisch $< 0.4$)
   - Contour outline and center centroid marker drawn with the respective confidence color.
   - Text label shows Cell ID and optionally confidence (e.g. `#1 (0.85)`).

4. **UI Metric Cards in `src/ui/app.py`:**
   - Display prominent metric cards in the results section:
     - `col1.metric("Gesamtzahl Zellen", summary["total_cells"])`
     - `col2.metric("Lebende Zellen", summary["live_cells"], delta=f"{summary['viability_pct']}% Viabilität")`
     - `col3.metric("Unsichere Zellen", summary["uncertain_cells"], help="Zellen mit Konfidenz 0.4 bis 0.7 (Gelb)")`
     - `col4.metric("Problematische Regionen", summary["problematic_cells"], help="Zellen mit Konfidenz < 0.4 (Rot)")`

5. **CSV Export in `src/utils/io_export.py` (`generate_csv_data`):**
   - Header updated to include `Confidence` column:
     `Cell_ID;Status;Confidence;X_px;Y_px;Area_px;Area_um2;Circularity;Solidity;I_Core;I_Ring;Intensity_Diff`
   - Formatted value: `c.get("confidence", 1.0)`.

---

## 3. Requirement 3 (R3): Manual Correction UI & JSON Persistence

### 3.1 Problem & Objective
In routine laboratory quality control, lab technicians must quickly adjust the cell count if specific edge cells were missed or extra debris was detected, without requiring tedious manual polygon editing. R3 provides:
1. A clean, rapid manual correction UI placed **directly below the Dual-Panel image comparison**.
2. A number input `Korrigierte Gesamtzahl` pre-filled with the algorithm's detected count.
3. Automatic delta computation ($\Delta = \text{corrected} - \text{original}$).
4. A `Korrektur speichern` button that writes full correction metadata and original image reference to `data/corrections/<timestamp>_<filename>.json`.

### 3.2 UI Design & Component Layout in `src/ui/app.py`

- **Position:** Placed right after the Dual-Panel image comparison columns (`col_img1`, `col_img2`) and before the cytometric charts / export sections.
- **Visual Structure:**
  ```markdown
  ---
  ### ✏️ Manuelle Zählkorrektur & Feedback
  [ Info-Box: "Passe die Gesamtzahl an, falls einzelne Zellen übersehen oder Artefakte gezählt wurden." ]
  
  [ Column 1: Number Input 'Korrigierte Gesamtzahl' (prefilled with summary['total_cells']) ]
  [ Column 2: Delta Metric Display (z.B. '+2 Zellen' oder '-1 Zelle') ]
  [ Column 3: Button '💾 Korrektur speichern' ]
  ```
- **Streamlit State Handling:**
  - The number input key is tied to `f"corrected_count_{filename}"`.
  - On button click, trigger the persistence function, display a success toast/banner with the saved file path, and prevent duplicate saves.

### 3.3 Persistence Schema & Storage Architecture

- **Directory:** `data/corrections/` (automatically created with `os.makedirs(..., exist_ok=True)`).
- **File Naming Pattern:** `<timestamp>_<filename>.json`
  - E.g.: `20260831_230500_synthetic_clean_cluster.png.json`
- **JSON Payload Format:**
  ```json
  {
    "original_count": 13,
    "corrected_count": 15,
    "delta": 2,
    "image_path": "tests/data/synthetic_clean_cluster.png",
    "timestamp": "2026-08-31T23:05:00.123456",
    "preset_name": "Standard_Brightfield",
    "markers": [
      {
        "cell_id": 1,
        "x_px": 100.0,
        "y_px": 100.0,
        "area_px": 706.86,
        "confidence": 0.88,
        "status": "LIVE"
      },
      {
        "cell_id": 2,
        "x_px": 200.0,
        "y_px": 100.0,
        "area_px": 1017.88,
        "confidence": 0.91,
        "status": "DEAD"
      }
    ]
  }
  ```
- **Implementation in `src/utils/io_export.py` (or `src/utils/corrections.py`):**
  ```python
  def save_manual_correction(
      filename: str,
      original_count: int,
      corrected_count: int,
      cell_list: List[Dict[str, Any]],
      image_path: str = "",
      output_dir: str = "data/corrections",
  ) -> str:
      """Speichert eine manuelle Zählkorrektur als strukturierte JSON-Datei für Re-Training.
      
      Args:
          filename: Name der Bilddatei.
          original_count: Vom Algorithmus ermittelte Zellzahl.
          corrected_count: Vom Nutzer manuell korrigierte Zellzahl.
          cell_list: Liste der segmentierten Zellen mit Koordinaten und Konfidenzen.
          image_path: Pfad zum Originalbild.
          output_dir: Zielordner für die Korrekturdaten.
          
      Returns:
          str: Pfad zur erstellten JSON-Datei.
      """
  ```

---

## 4. Codebase Architecture & File Mapping

The table below maps all planned changes to project files according to `GEMINI.md` standards:

| File Path | Role | Planned Modifications for R1, R2, R3 |
|---|---|---|
| `src/core/preprocessing.py` | Core (Image Processing) | Add `auto_calibrate_parameters(gray, base_params)` performing histogram, local contrast, and illumination gradient analysis. Log at `INFO` level. |
| `src/core/segmentation.py` | Core (Segmentation) | Integrate / invoke confidence metric calculation during or after contour filtering; assign confidence scores and classes to each cell dictionary. |
| `src/core/metrics.py` | Core (Statistics) | Update `compute_summary_statistics` to compute `uncertain_cells` (yellow), `problematic_cells` (red), `high_confidence_cells` (green), and `mean_confidence`. |
| `src/utils/io_export.py` | Utils (I/O & Overlays) | 1. Update `create_annotated_overlay` to color-code cells by confidence (Green $\ge 0.7$, Yellow $0.4-0.7$, Red $< 0.4$).<br>2. Update `generate_csv_data` to output the `Confidence` column.<br>3. Add `save_manual_correction` saving JSON records to `data/corrections/<timestamp>_<filename>.json`. |
| `src/ui/components.py` | UI (Sidebar & Controls) | Add auto-calibration toggle in the sidebar; initialize slider defaults from calibrated parameters while preserving manual overrides. |
| `src/ui/app.py` | UI (Main App) | 1. Integrate auto-calibration workflow in Tab 1.<br>2. Update Metric Cards to show "Unsichere Zellen: X" and "Problematische Regionen: Y".<br>3. Add Manual Correction UI section directly below the Dual-Panel image comparison. |
| `tests/test_preprocessing.py` or `tests/test_calibration.py` | Tests | Add unit tests for `auto_calibrate_parameters` across synthetic test images (verifying detected cell count $\ge$ fixed config and valid parameter ranges). |
| `tests/test_segmentation.py` or `tests/test_confidence.py` | Tests | Add unit tests verifying confidence scores $\in [0, 1]$, proper categorization into Green/Yellow/Red, and presence of confidence in cell dictionaries. |
| `tests/test_io_export.py` or `tests/test_database.py` | Tests | Add unit tests verifying CSV export with `confidence` column and manual correction JSON file saving/reading. |

---

## 5. Verification & Test Strategy

### 5.1 Existing Test Suite Baseline
- Existing suite: 10 tests across `tests/test_database.py`, `tests/test_preprocessing.py`, `tests/test_segmentation.py`, `tests/test_tiff.py`, `tests/test_viability.py`.
- Execution command: `uv run pytest -v` (all 10 passing).

### 5.2 Acceptance Criteria Verification Matrix
1. **R1 Calibration Acceptance:**
   - Test against 3 synthetic images: `synthetic_clean_cluster.png`, `synthetic_vignetting_gradient.png`, `synthetic_dust_artifacts.png`.
   - Verify cell count with auto-calibration $\ge$ fixed baseline count (currently 7, target $\ge 7$, ideally 10–13 cells).
   - Check `logs/cell_counter.log` contains INFO-level calibration entries.
2. **R2 Confidence Acceptance:**
   - Verify every cell has a confidence score $\in [0.0, 1.0]$ and a color classification.
   - Verify overlay outputs Green/Yellow/Red annotations.
   - Verify CSV export contains the `confidence` column.
   - Verify metric cards display `Unsichere Zellen: X` and `Problematische Regionen: Y`.
3. **R3 Correction Acceptance:**
   - Test UI input and JSON saving helper.
   - Verify generated JSON file in `data/corrections/<timestamp>_<filename>.json` contains all required fields: `original_count`, `corrected_count`, `delta`, `markers`, `image_path`.

---

## 6. Conclusion & Recommended Next Steps

The system architecture is clean, modular, and ready for the implementation of R1, R2, and R3 without breaking backwards compatibility. The survey provides the complete roadmap for the upcoming implementation phase.
