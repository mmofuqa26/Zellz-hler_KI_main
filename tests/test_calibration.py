"""Unit-Tests für das Auto-Kalibrierungsmodul (R1 Bildstatistik & Parameteranpassung)."""

import logging
import os
import cv2
import numpy as np
import pytest

from src.core.calibration import (
    BOUNDS_ADAPTIVE_BLOCK_SIZE,
    BOUNDS_ADAPTIVE_C,
    BOUNDS_CLAHE_CLIP,
    BOUNDS_DIST_THRESHOLD_RATIO,
    BOUNDS_MIN_MARKER_AREA,
    analyze_image_statistics,
    auto_calibrate_parameters,
)
from src.core.preprocessing import apply_clahe, denoise_image
from src.core.segmentation import segment_cells
from tests.generate_test_images import create_all_test_images


@pytest.fixture(scope="module")
def setup_test_images():
    """Generiert die synthetischen Testbilder für die Unit-Tests."""
    test_files = create_all_test_images("tests/data")
    return test_files


def test_analyze_image_statistics(setup_test_images):
    """Verifiziert die Extraktion aller statistischen Merkmale auf den Testbildern."""
    clean_path = "tests/data/synthetic_clean_cluster.png"
    vignette_path = "tests/data/synthetic_vignetting_gradient.png"
    dust_path = "tests/data/synthetic_dust_artifacts.png"

    for path in [clean_path, vignette_path, dust_path]:
        assert os.path.exists(path)
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        stats = analyze_image_statistics(img)

        # Alle geforderten Schlüssel müssen vorhanden sein
        expected_keys = [
            "mean",
            "std",
            "p10",
            "p50",
            "p90",
            "dynamic_range",
            "laplacian_var",
            "gradient_magnitude",
            "radial_gradient_ratio",
            "radial_gradient",
        ]
        for key in expected_keys:
            assert key in stats, f"Schlüssel '{key}' fehlt in Bildstatistiken"
            assert isinstance(stats[key], (int, float)), f"Wert für '{key}' ist kein Float/Int"
            assert not np.isnan(stats[key]), f"Wert für '{key}' ist NaN"
            assert not np.isinf(stats[key]), f"Wert für '{key}' ist unendlich"

    # Bildspezifische Eigenschaften prüfen
    img_vignette = cv2.imread(vignette_path, cv2.IMREAD_GRAYSCALE)
    stats_vignette = analyze_image_statistics(img_vignette)
    # Vignettiertes Bild hat dunklere Ränder -> radial_gradient_ratio < 1.0
    assert stats_vignette["radial_gradient_ratio"] < 0.90

    img_dust = cv2.imread(dust_path, cv2.IMREAD_GRAYSCALE)
    stats_dust = analyze_image_statistics(img_dust)
    img_clean = cv2.imread(clean_path, cv2.IMREAD_GRAYSCALE)
    stats_clean = analyze_image_statistics(img_clean)
    # Staub & Rauschen erhöhen die Laplace-Varianz signifikant
    assert stats_dust["laplacian_var"] > stats_clean["laplacian_var"]


def test_auto_calibration_parameter_bounds(setup_test_images):
    """Verifiziert, dass alle auto-kalibrierten Parameter innerhalb sicherer Intervalle liegen."""
    test_paths = [
        "tests/data/synthetic_clean_cluster.png",
        "tests/data/synthetic_vignetting_gradient.png",
        "tests/data/synthetic_dust_artifacts.png",
    ]

    for path in test_paths:
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        calibrated_params, stats = auto_calibrate_parameters(img)

        # 1. CLAHE Clip Limit
        clahe_clip = calibrated_params["clahe_clip_limit"]
        assert isinstance(clahe_clip, float)
        assert BOUNDS_CLAHE_CLIP[0] <= clahe_clip <= BOUNDS_CLAHE_CLIP[1]

        # 2. Adaptive Thresh Block Size (ungerader int)
        block_size = calibrated_params["adaptive_thresh_block_size"]
        assert isinstance(block_size, int)
        assert block_size % 2 == 1, f"Blockgröße {block_size} muss ungerade sein"
        assert BOUNDS_ADAPTIVE_BLOCK_SIZE[0] <= block_size <= BOUNDS_ADAPTIVE_BLOCK_SIZE[1]

        # 3. Adaptive Thresh C
        c_val = calibrated_params["adaptive_thresh_c"]
        assert isinstance(c_val, int)
        assert BOUNDS_ADAPTIVE_C[0] <= c_val <= BOUNDS_ADAPTIVE_C[1]

        # 4. Min Marker Area
        min_marker = calibrated_params["min_marker_area_px"]
        assert isinstance(min_marker, int)
        assert BOUNDS_MIN_MARKER_AREA[0] <= min_marker <= BOUNDS_MIN_MARKER_AREA[1]

        # 5. Dist Threshold Ratio
        dist_ratio = calibrated_params["dist_threshold_ratio"]
        assert isinstance(dist_ratio, float)
        assert BOUNDS_DIST_THRESHOLD_RATIO[0] <= dist_ratio <= BOUNDS_DIST_THRESHOLD_RATIO[1]


def test_auto_calibration_cell_count_baseline(setup_test_images):
    """Verifiziert, dass mit Auto-Kalibrierung mindestens 7 Zellen auf allen Testbildern erkannt werden."""
    test_images = [
        "tests/data/synthetic_clean_cluster.png",
        "tests/data/synthetic_vignetting_gradient.png",
        "tests/data/synthetic_dust_artifacts.png",
    ]

    for img_path in test_images:
        assert os.path.exists(img_path)
        img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)

        calibrated_params, stats = auto_calibrate_parameters(img)

        # Vorverarbeitung mit kalibriertem CLAHE Clip-Limit
        clahe_img = apply_clahe(img, clip_limit=calibrated_params["clahe_clip_limit"])
        denoised_img = denoise_image(clahe_img)

        # Segmentierung mit kalibrierten Parametern
        cells, markers, binary = segment_cells(denoised_img, calibrated_params)

        assert len(cells) >= 7, (
            f"Zu wenige Zellen ({len(cells)}) auf {img_path} mit Parametern {calibrated_params} erkannt."
        )


def test_auto_calibration_logging(caplog):
    """Verifiziert, dass die Auto-Kalibrierung detaillierte INFO-Logs ausgibt."""
    img = np.full((300, 300), 200, dtype=np.uint8)
    cv2.circle(img, (150, 150), 30, 50, -1)

    with caplog.at_level(logging.INFO):
        calibrated_params, stats = auto_calibrate_parameters(img)

    # Prüfe, ob INFO-Log ausgegeben wurde
    assert any("Auto-Kalibrierung" in record.message for record in caplog.records)
    assert any(record.levelno == logging.INFO for record in caplog.records)


def test_analyze_image_statistics_input_validation():
    """Testet die Fehlerbehandlung bei ungültigen Eingabedaten."""
    with pytest.raises(TypeError):
        analyze_image_statistics("not_an_array")

    with pytest.raises(ValueError):
        analyze_image_statistics(np.array([]))

    with pytest.raises(ValueError):
        analyze_image_statistics(np.zeros((10, 10, 10, 10), dtype=np.uint8))


def test_auto_calibration_base_params_preservation():
    """Testet, dass benutzerdefinierte Parameter im Basis-Wörterbuch erhalten bleiben."""
    img = np.full((200, 200), 180, dtype=np.uint8)
    custom_base = {
        "custom_user_annotation": "HEK293_Run_42",
        "min_cell_diameter_px": 18,
        "max_cell_diameter_px": 140,
    }

    calibrated_params, stats = auto_calibrate_parameters(img, base_params=custom_base)

    assert calibrated_params["custom_user_annotation"] == "HEK293_Run_42"
    assert calibrated_params["min_cell_diameter_px"] == 18
    assert calibrated_params["max_cell_diameter_px"] == 140
    assert "clahe_clip_limit" in calibrated_params
    assert "adaptive_thresh_block_size" in calibrated_params


def test_auto_calibration_extreme_images():
    """Verifiziert Stabilität bei extremen Bildern (komplett schwarz, komplett weiß)."""
    black_img = np.zeros((200, 200), dtype=np.uint8)
    white_img = np.full((200, 200), 255, dtype=np.uint8)

    for extreme_img in [black_img, white_img]:
        stats = analyze_image_statistics(extreme_img)
        assert stats["mean"] in (0.0, 255.0)
        assert stats["dynamic_range"] == 0.0

        params, _ = auto_calibrate_parameters(extreme_img)
        assert BOUNDS_CLAHE_CLIP[0] <= params["clahe_clip_limit"] <= BOUNDS_CLAHE_CLIP[1]
        assert BOUNDS_ADAPTIVE_BLOCK_SIZE[0] <= params["adaptive_thresh_block_size"] <= BOUNDS_ADAPTIVE_BLOCK_SIZE[1]
        assert params["adaptive_thresh_block_size"] % 2 == 1
