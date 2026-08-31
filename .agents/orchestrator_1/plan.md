# Orchestration Plan: CellCounter Pro Enhancements

## 1. Objectives
Implement three functional enhancements to CellCounter Pro:
1. **R1: Automatic Parameter Calibration per Image**
   - Statistical image analysis (histogram distribution, local contrast, brightness gradient).
   - Adaptive Watershed parameters (threshold, CLAHE clip limit, min marker area, distance ratio).
   - Sidebar slider overrides preserved.
   - INFO-level logging of calibration parameters.
2. **R2: Confidence Traffic Light per Cell Region**
   - Confidence score [0..1] based on circularity, solidity, local CNR.
   - Annotated overlay coloring: Green (>=0.7), Yellow (0.4..0.7), Red (<0.4).
   - Prominent metrics: "Unsichere Zellen: X", "Problematische Regionen: Y".
   - CSV export with 'confidence' column.
3. **R3: Manual Correction UI**
   - Under dual-panel: number input 'Korrigierte Gesamtzahl' prefilled with algorithm count.
   - 'Korrektur speichern' button saving JSON to `data/corrections/<timestamp>_<filename>.json` with `{original_count, corrected_count, delta, markers, image_path}`.
4. **Acceptance Criteria & Quality**
   - 10 existing Pytest tests pass.
   - >=2 new unit tests for auto-calibration and confidence scoring.
   - Auto-calibration on 3 test images yields >= cell count vs fixed config.
   - GEMINI.md compliance (Python 3.11+, typing, Google docstrings, specific exceptions, logging, architecture separation).

## 2. Phases & Workflow
- **Phase 0: Survey** (Parallel Explorers)
  - Map project directory, modules (`core/`, `ui/`, `utils/`, `tests/`), configurations, data flows.
- **Phase 1: Project Blueprint (`PROJECT.md`)**
  - Synthesize findings, map out interfaces, data schemas, module boundaries, milestone decomposition.
- **Phase 2: Milestone Iteration Loop**
  - Explorer -> Worker -> Reviewer -> Challenger -> Auditor -> Gate
  - Milestone 1: Calibration Engine (Core + Config + Logging)
  - Milestone 2: Confidence Engine & Region Analysis (Core + Visualizations)
  - Milestone 3: Manual Correction & Storage Subsystem (Utils / Core)
  - Milestone 4: Streamlit UI Integration & Export (UI / CSV / Overlay)
- **Phase 3: E2E Verification & Test Suite Execution**
  - Run full pytest test suite, test image comparisons.
  - Reviewer & Challenger verification.
  - Independent Forensic Integrity Audit.
- **Phase 4: Synthesis & Human Report to Sentinel**
