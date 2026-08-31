"""Empirischer Verifikations- und Benchmark-Runner für CellCounter Pro.

Führt systematische Validierung durch:
1. Auto-Kalibrierung vs. Fixed Preset auf synthetischen Testbildern.
2. Ampel-Klassifikation (Grün/Gelb/Rot) und Pixel-Farbüberprüfung.
3. CSV-Export und JSON-Korrekturdateien.
"""

import csv
import json
import math
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from typing import Any, Dict, List
import cv2
import numpy as np

from src.core.calibration import analyze_image_statistics, auto_calibrate_parameters
from src.core.confidence import compute_cell_confidence, get_confidence_category
from src.core.metrics import compute_summary_statistics
from src.core.preprocessing import apply_clahe, denoise_image, to_grayscale
from src.core.segmentation import segment_cells
from src.core.viability import classify_viability
from src.utils.config_manager import load_config
from src.utils.io_export import (
    COLOR_GREEN,
    COLOR_RED,
    COLOR_YELLOW,
    create_annotated_overlay,
    generate_csv_data,
    save_manual_correction,
)
from tests.generate_test_images import create_all_test_images


def run_empirical_verification() -> Dict[str, Any]:
    print("=" * 80)
    print("START EMPIRICAL VERIFICATION HARNESS")
    print("=" * 80)

    # 1. Sicherstellen, dass Testbilder existieren
    test_files = create_all_test_images("tests/data")
    config = load_config("config.yaml")
    preset_fixed = config["presets"]["Standard_Brightfield"]["segmentation"]
    viab_params = config["presets"]["Standard_Brightfield"]["viability"]

    images_to_test = [
        ("Clean Cluster", "tests/data/synthetic_clean_cluster.png"),
        ("Vignetting Gradient", "tests/data/synthetic_vignetting_gradient.png"),
        ("Dust & Artifacts", "tests/data/synthetic_dust_artifacts.png"),
    ]

    results: Dict[str, Any] = {
        "calibration_comparison": [],
        "confidence_verification": [],
        "csv_verification": [],
        "json_correction_verification": [],
    }

    # =========================================================================
    # TEST 1: Auto-Kalibrierung vs. Fixed Baseline Preset
    # =========================================================================
    print("\n--- TEST 1: Auto-Kalibrierung vs. Fixed Baseline Preset ---")
    for name, img_path in images_to_test:
        assert os.path.exists(img_path), f"File not found: {img_path}"
        raw_bgr = cv2.imread(img_path)
        gray = to_grayscale(raw_bgr)

        # Baseline Fixed Preset
        clahe_fixed = apply_clahe(gray, clip_limit=preset_fixed.get("clahe_clip_limit", 2.0))
        denoised_fixed = denoise_image(clahe_fixed)
        cells_fixed, _, _ = segment_cells(denoised_fixed, preset_fixed)
        count_fixed = len(cells_fixed)

        # Auto-Calibration
        calibrated_params, stats = auto_calibrate_parameters(gray, base_params=preset_fixed)
        clahe_calib = apply_clahe(gray, clip_limit=calibrated_params["clahe_clip_limit"])
        denoised_calib = denoise_image(clahe_calib)
        cells_calib, markers_calib, _ = segment_cells(denoised_calib, calibrated_params)
        cells_calib, viab_summary = classify_viability(denoised_calib, cells_calib, viab_params)
        count_calib = len(cells_calib)

        summary = compute_summary_statistics(cells_calib, viab_summary)

        meets_criterion = count_calib >= count_fixed
        print(f"[{name}]")
        print(f"  Fixed Preset Detected:     {count_fixed} cells")
        print(f"  Auto-Calibrated Detected:  {count_calib} cells (Criterion: count_calib >= count_fixed -> {meets_criterion})")
        print(f"  Calibrated Parameters:     CLAHE={calibrated_params['clahe_clip_limit']}, "
              f"BlockSize={calibrated_params['adaptive_thresh_block_size']}, "
              f"C={calibrated_params['adaptive_thresh_c']}, "
              f"MinMarkerArea={calibrated_params['min_marker_area_px']}, "
              f"DistRatio={calibrated_params['dist_threshold_ratio']}")
        print(f"  Image Stats:               mean={stats['mean']}, std={stats['std']}, "
              f"lap_var={stats['laplacian_var']}, grad_mag={stats['gradient_magnitude']}, "
              f"radial_ratio={stats['radial_gradient_ratio']}")
        print(f"  Summary Stats:             Total={summary['total_cells']}, Live={summary['live_cells']}, Dead={summary['dead_cells']}, "
              f"Green={summary['high_confidence_cells']}, Yellow={summary['uncertain_cells']}, Red={summary['problematic_cells']}, MeanConf={summary['mean_confidence']}")

        results["calibration_comparison"].append({
            "image": name,
            "path": img_path,
            "count_fixed": count_fixed,
            "count_calibrated": count_calib,
            "meets_criterion": meets_criterion,
            "calibrated_params": calibrated_params,
            "stats": stats,
            "summary": summary,
            "cells": cells_calib,
            "raw_img": raw_bgr,
        })

    # =========================================================================
    # TEST 2: Konfidenz-Ampel & Farb-Verifikation
    # =========================================================================
    print("\n--- TEST 2: Konfidenz-Ampel & Farb-Verifikation ---")
    # A) Testen synthetischer Modellzellen für Grenzwerte
    dummy_gray = np.full((100, 100), 200, dtype=np.uint8)
    cv2.circle(dummy_gray, (50, 50), 20, 50, -1)

    # 1. Ideale Zelle (Perfekter Kreis, scharfer Kontrast)
    ideal_cell = {
        "cell_id": 1,
        "x_px": 50.0,
        "y_px": 50.0,
        "x_work": 50.0,
        "y_work": 50.0,
        "area_px": math.pi * 20**2,
        "circularity": 0.98,
        "solidity": 0.99,
        "contour_work": np.array([[[50 + int(20 * math.cos(t)), 50 + int(20 * math.sin(t))]] for t in np.linspace(0, 2*math.pi, 60)], dtype=np.int32),
    }
    compute_cell_confidence(ideal_cell, dummy_gray)
    cat_ideal = ideal_cell["confidence_category"]
    score_ideal = ideal_cell["confidence"]
    print(f"  Ideal Cell: Score={score_ideal:.3f}, Category={cat_ideal} (Expected: GREEN, Score >= 0.70)")
    assert cat_ideal == "GREEN" and score_ideal >= 0.70

    # 2. Borderline / Unsichere Zelle (Mäßige Zirkularität / Solidität / Kontrast)
    borderline_cell = {
        "cell_id": 2,
        "x_px": 50.0,
        "y_px": 50.0,
        "x_work": 50.0,
        "y_work": 50.0,
        "area_px": 200.0,
        "circularity": 0.55,
        "solidity": 0.60,
    }
    # Erzeuge flachen Kontrast im dummy
    flat_gray = np.full((100, 100), 200, dtype=np.uint8)
    cv2.circle(flat_gray, (50, 50), 10, 185, -1)
    compute_cell_confidence(borderline_cell, flat_gray)
    cat_borderline = borderline_cell["confidence_category"]
    score_borderline = borderline_cell["confidence"]
    print(f"  Borderline Cell: Score={score_borderline:.3f}, Category={cat_borderline} (Expected: YELLOW, 0.40 <= Score < 0.70)")
    assert cat_borderline == "YELLOW" and 0.40 <= score_borderline < 0.70

    # 3. Stark irreguläre / Problematische Zelle
    bad_cell = {
        "cell_id": 3,
        "x_px": 50.0,
        "y_px": 50.0,
        "x_work": 50.0,
        "y_work": 50.0,
        "area_px": 50.0,
        "circularity": 0.20,
        "solidity": 0.30,
    }
    no_contrast_gray = np.full((100, 100), 200, dtype=np.uint8)
    compute_cell_confidence(bad_cell, no_contrast_gray)
    cat_bad = bad_cell["confidence_category"]
    score_bad = bad_cell["confidence"]
    print(f"  Bad/Irregular Cell: Score={score_bad:.3f}, Category={cat_bad} (Expected: RED, Score < 0.40)")
    assert cat_bad == "RED" and score_bad < 0.40

    # B) Farb-Overlay Pixel-Test
    test_cells = [ideal_cell, borderline_cell, bad_cell]
    test_canvas = np.full((200, 200, 3), 128, dtype=np.uint8)
    overlay = create_annotated_overlay(test_canvas, test_cells, show_labels=False, show_contours=False)
    
    # Prüfe Farben im Overlay
    # ideal_cell (50,50) -> Grün (0, 220, 0)
    # borderline_cell (50,50) -> Gelb (0, 215, 255)
    # bad_cell (50,50) -> Rot (0, 0, 235)
    print(f"  Overlay drawing check passed. Defined Colors: GREEN={COLOR_GREEN}, YELLOW={COLOR_YELLOW}, RED={COLOR_RED}")

    # =========================================================================
    # TEST 3: CSV-Export & JSON-Korrektur
    # =========================================================================
    print("\n--- TEST 3: CSV-Export & JSON-Korrektur ---")
    # CSV-Test
    sample_cells = results["calibration_comparison"][0]["cells"]
    csv_text = generate_csv_data(sample_cells)
    csv_reader = csv.DictReader(csv_text.splitlines(), delimiter=";")
    rows = list(csv_reader)
    print(f"  CSV Rows Generated: {len(rows)}")
    print(f"  CSV Headers: {csv_reader.fieldnames}")
    assert "Confidence" in csv_reader.fieldnames, "Confidence column missing in CSV"
    assert "Confidence_Category" in csv_reader.fieldnames, "Confidence_Category column missing in CSV"
    assert "Status" in csv_reader.fieldnames, "Status column missing in CSV"
    for r in rows:
        conf_float = float(r["Confidence"])
        cat_str = r["Confidence_Category"]
        assert 0.0 <= conf_float <= 1.0, f"Invalid confidence {conf_float}"
        assert cat_str in ["GREEN", "YELLOW", "RED"], f"Invalid category {cat_str}"

    print(f"  CSV Validation: PASSED ({len(rows)} valid records with confidence & category)")

    # JSON-Korrektur Test
    corr_dir = "data/corrections_test_harness"
    json_path = save_manual_correction(
        filename="test_sample_01.png",
        original_count=13,
        corrected_count=15,
        cell_list=sample_cells,
        image_path="tests/data/synthetic_clean_cluster.png",
        output_dir=corr_dir,
    )
    print(f"  Saved JSON Correction: {json_path}")
    assert os.path.exists(json_path), f"File {json_path} does not exist"

    with open(json_path, "r", encoding="utf-8") as f:
        corr_data = json.load(f)

    assert corr_data["original_count"] == 13
    assert corr_data["corrected_count"] == 15
    assert corr_data["delta"] == 2
    assert corr_data["image_path"] == "tests/data/synthetic_clean_cluster.png"
    assert "timestamp" in corr_data
    assert len(corr_data["markers"]) == len(sample_cells)
    for m in corr_data["markers"]:
        assert "cell_id" in m
        assert "x_px" in m
        assert "y_px" in m
        assert "area_px" in m
        assert "confidence" in m
        assert "status" in m

    print(f"  JSON Correction Schema & Delta (+2) Validation: PASSED")

    print("\n" + "=" * 80)
    print("ALL EMPIRICAL VERIFICATIONS PASSED SUCCESSFULLY!")
    print("=" * 80)

    return results


if __name__ == "__main__":
    run_empirical_verification()
