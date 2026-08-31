"""Unit- und Integrationstests für die UI-Komponenten und den Workflow von CellCounter Pro.

Testet Sidebar-Rendern, Auto-Kalibrierungs-Optionen, Parameter-Overrides,
Metriken-Generierung für Metric Cards und manuelle Korrektur-Integration.
"""

import json
import os
import tempfile
from typing import Any, Dict
from unittest.mock import MagicMock, patch
import cv2
import numpy as np
import pytest

from src.core.calibration import auto_calibrate_parameters
from src.core.metrics import compute_summary_statistics
from src.core.preprocessing import apply_clahe, denoise_image, to_grayscale
from src.core.segmentation import segment_cells
from src.core.viability import classify_viability
from src.ui.components import render_sidebar
from src.utils.config_manager import load_config
from src.utils.io_export import create_annotated_overlay, save_manual_correction


@pytest.fixture
def dummy_config() -> Dict[str, Any]:
    """Erzeugt eine Testkonfiguration."""
    return {
        "default_preset": "Standard_Brightfield",
        "presets": {
            "Standard_Brightfield": {
                "description": "Standard-Hellfeld-Mikroskopie",
                "segmentation": {
                    "min_cell_diameter_px": 12,
                    "max_cell_diameter_px": 120,
                    "adaptive_thresh_block_size": 21,
                    "adaptive_thresh_c": 5,
                    "min_marker_area_px": 3,
                    "dist_threshold_ratio": 0.25,
                    "clahe_clip_limit": 2.0,
                    "min_circularity": 0.35,
                    "min_solidity": 0.50,
                },
                "viability": {
                    "enabled": True,
                    "ring_width_px": 4,
                    "intensity_diff_threshold": -12.0,
                },
                "preprocessing": {
                    "max_dimension": 2048,
                },
            }
        },
    }


def test_render_sidebar_defaults(dummy_config: Dict[str, Any]) -> None:
    """Testet, dass render_sidebar Standardparameter und Auto-Kalibrierung zurückgibt."""
    with patch("streamlit.sidebar") as mock_sb:
        mock_sb.selectbox.return_value = "Standard_Brightfield"
        mock_sb.checkbox.side_effect = [True, True]  # auto_calibrate, viab_enabled
        mock_sb.slider.side_effect = [
            (12, 120),  # diameter
            0.25,       # dist_ratio
            21,         # block_size
            2.0,        # clahe_clip
            0.35,       # min_circularity
            -12.0,      # intensity_diff
            4,          # ring_width
        ]
        mock_sb.number_input.side_effect = [
            3,          # min_marker_area
            0.0,        # um_per_pixel
        ]
        mock_sb.expander.return_value.__enter__.return_value = mock_sb
        mock_sb.expander.return_value.__exit__.return_value = None

        seg_params, viab_params, active_preset, auto_cal = render_sidebar(dummy_config)

        assert active_preset == "Standard_Brightfield"
        assert auto_cal is True
        assert seg_params["auto_calibrate"] is True
        assert seg_params["min_cell_diameter_px"] == 12
        assert seg_params["max_cell_diameter_px"] == 120
        assert seg_params["dist_threshold_ratio"] == 0.25
        assert seg_params["min_marker_area_px"] == 3
        assert seg_params["adaptive_thresh_block_size"] == 21
        assert seg_params["clahe_clip_limit"] == 2.0
        assert viab_params["enabled"] is True


def test_render_sidebar_with_calibrated_params(dummy_config: Dict[str, Any]) -> None:
    """Testet, dass render_sidebar auto-kalibrierte Werte als Basis übernimmt."""
    calibrated_params = {
        "clahe_clip_limit": 3.2,
        "adaptive_thresh_block_size": 27,
        "adaptive_thresh_c": 6,
        "min_marker_area_px": 5,
        "dist_threshold_ratio": 0.30,
    }

    with patch("streamlit.sidebar") as mock_sb:
        mock_sb.selectbox.return_value = "Standard_Brightfield"
        mock_sb.checkbox.side_effect = [True, True]
        mock_sb.slider.side_effect = [
            (12, 120),
            0.30,
            27,
            3.2,
            0.35,
            -12.0,
            4,
        ]
        mock_sb.number_input.side_effect = [
            5,
            0.0,
        ]
        mock_sb.expander.return_value.__enter__.return_value = mock_sb
        mock_sb.expander.return_value.__exit__.return_value = None

        seg_params, viab_params, active_preset, auto_cal = render_sidebar(
            dummy_config, calibrated_params=calibrated_params
        )

        assert auto_cal is True
        assert seg_params["clahe_clip_limit"] == 3.2
        assert seg_params["adaptive_thresh_block_size"] == 27
        assert seg_params["adaptive_thresh_c"] == 6
        assert seg_params["min_marker_area_px"] == 5
        assert seg_params["dist_threshold_ratio"] == 0.30


def test_ui_analysis_pipeline_integration() -> None:
    """Testet die vollständige Pipeline für die UI: Kalibrierung -> Segmentierung -> Metriken -> Overlay."""
    # Synthetisches Testbild erzeugen
    img = np.ones((256, 256), dtype=np.uint8) * 200
    # 4 Kreiszellen
    for cx, cy in [(60, 60), (60, 180), (180, 60), (180, 180)]:
        cv2.circle(img, (cx, cy), 18, 50, -1)

    gray = to_grayscale(img)

    base_seg_params = {
        "min_cell_diameter_px": 10,
        "max_cell_diameter_px": 100,
        "adaptive_thresh_block_size": 21,
        "adaptive_thresh_c": 5,
        "min_marker_area_px": 2,
        "dist_threshold_ratio": 0.20,
        "min_circularity": 0.30,
        "min_solidity": 0.50,
    }

    # 1. Auto-Kalibrierung
    calib_params, stats = auto_calibrate_parameters(gray, base_params=base_seg_params)
    assert "clahe_clip_limit" in calib_params
    assert "adaptive_thresh_block_size" in calib_params

    # 2. Preprocessing & Segmentierung
    clahe = apply_clahe(gray, clip_limit=calib_params.get("clahe_clip_limit", 2.0))
    denoised = denoise_image(clahe)
    cells, markers, binary = segment_cells(denoised, calib_params)

    assert len(cells) >= 4

    # 3. Viabilität & Metriken
    viab_params = {"enabled": True, "ring_width_px": 4, "intensity_diff_threshold": -12.0}
    cells, viab_summary = classify_viability(denoised, cells, viab_params)
    summary = compute_summary_statistics(cells, viab_summary)

    # 4. Überprüfung der Metric Card Felder
    assert "total_cells" in summary
    assert "live_cells" in summary
    assert "uncertain_cells" in summary
    assert "problematic_cells" in summary
    assert summary["total_cells"] == len(cells)

    # 5. Overlay Erzeugung
    overlay = create_annotated_overlay(img, cells, show_labels=True, show_contours=True)
    assert overlay.shape == (256, 256, 3)

    # 6. Manuelle Korrektur speichern
    with tempfile.TemporaryDirectory() as tmpdir:
        json_path = save_manual_correction(
            filename="test_sample.png",
            original_count=summary["total_cells"],
            corrected_count=summary["total_cells"] + 2,
            cell_list=cells,
            image_path="tests/data/synthetic_clean_cluster.png",
            output_dir=tmpdir,
        )
        assert os.path.exists(json_path)
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["original_count"] == summary["total_cells"]
        assert data["corrected_count"] == summary["total_cells"] + 2
        assert data["delta"] == 2
        assert len(data["markers"]) == len(cells)
