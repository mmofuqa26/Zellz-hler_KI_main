## 2026-08-31T21:04:23Z
You are teamwork_preview_explorer_survey_2.
Your working directory is c:\Users\miran\Documents\Zellzählerki\antigravity\.agents\teamwork_preview_explorer_survey_2\
Read the original user request at c:\Users\miran\Documents\Zellzählerki\antigravity\.agents\ORIGINAL_REQUEST.md and the project guidelines at c:\Users\miran\Documents\Zellzählerki\antigravity\GEMINI.md.

TASK:
Survey the feature requirements and existing UI / visualization / export points:
1. Analyze Requirement 1 (R1: Automatic parameter calibration per image based on histogram, local contrast, brightness gradient; slider override preservation; INFO-level logging). Map where calibration logic belongs (in core) and how UI sliders should connect.
2. Analyze Requirement 2 (R2: Confidence score per cell based on circularity, solidity, local CNR -> Green >=0.7, Yellow 0.4..0.7, Red <0.4; overlay visualization; metric cards "Unsichere Zellen: X", "Problematische Regionen: Y"; CSV export with 'confidence' column). Map where contour metrics are computed, how overlay drawing works, and how CSV export is handled.
3. Analyze Requirement 3 (R3: Manual correction UI below dual-panel; number input 'Korrigierte Gesamtzahl' prefilled with algorithm count; 'Korrektur speichern' button saving JSON to data/corrections/<timestamp>_<filename>.json with {original_count, corrected_count, delta, markers, image_path}). Map where UI goes and how persistence is structured.

Produce a detailed survey report at c:\Users\miran\Documents\Zellzählerki\antigravity\.agents\teamwork_preview_explorer_survey_2\survey_features.md and send a completion message with the path when finished.
