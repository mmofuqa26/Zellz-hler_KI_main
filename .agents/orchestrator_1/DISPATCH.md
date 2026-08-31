# DISPATCH LOG

## 2026-08-31T21:03:57Z
You are the Project Orchestrator for the CellCounter Pro enhancements project.

# Project Context & Workspace
- Workspace Root: c:\Users\miran\Documents\Zellzählerki\antigravity
- Your working directory: c:\Users\miran\Documents\Zellzählerki\antigravity\.agents\orchestrator_1\
- Original Request File: c:\Users\miran\Documents\Zellzählerki\antigravity\.agents\ORIGINAL_REQUEST.md
- GEMINI.md project standards:
  * Python 3.11+ with type hints
  * OpenCV, NumPy, Streamlit, Plotly, Pytest
  * Google-style docstrings for all functions
  * Specific exceptions (no bare except)
  * No hardcoded paths (use Config / CLI args)
  * Logging instead of print()
  * PEP 8 compliant
  * Architecture separation: Core (image processing) | UI (Streamlit) | Utils (helpers) - no business logic in UI
  * Tests: Unit tests for image processing, test synthetic images in tests/data/, run tests before and after changes.

# Task Overview
Implement the three required extensions for CellCounter Pro:
1. R1: Automatic parameter calibration per image (histogram, local contrast, brightness gradient -> adaptive Watershed parameters, slider override preserved, INFO-level logging).
2. R2: Confidence traffic light per cell region (confidence score 0..1 based on circularity, solidity, local CNR -> Green >=0.7, Yellow 0.4..0.7, Red <0.4; metrics show uncertain/problematic counts; CSV export includes 'confidence' column).
3. R3: Manual correction UI (number input for corrected total pre-filled with algorithm count; 'Korrektur speichern' button saving original image + markers + delta to data/corrections/<timestamp>_<filename>.json).
4. Acceptance criteria & Tests: All existing 10 pytest tests continue to pass (pytest -v), plus at least 2 new unit tests for confidence scoring and auto-calibration. Auto-calibration on 3 test images yields >= cell count of fixed config.

Please orchestrate specialists (explorers, implementers, reviewers/testers) to complete this task thoroughly. Maintain your plan.md, progress.md, and briefing. Report back to the Sentinel when complete.
