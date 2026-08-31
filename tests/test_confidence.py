"""Unit-Tests für das Konfidenz- und Exportmodul (R2).

Testet:
1. Konfidenz-Score-Normalisierung, Rundung und Ampel-Kategorien (GREEN, YELLOW, RED)
2. Geometrische und Kontrast-Strafen bei unregelmäßigen / kontrastarmen Formen
3. Aggregation der Konfidenzmetriken in compute_summary_statistics
4. CSV-Export mit Spalten 'Confidence' und 'Confidence_Category'
5. Zeichnen der Ampelfarben (Grün, Gelb, Rot) im annotierten Overlay-Bild
6. Automatische Konfidenz-Anreicherung im Segmentierungs-Workflow
"""

import csv
import io
import os
import cv2
import numpy as np
import pytest

from src.core.confidence import (
    compute_cell_confidence,
    get_confidence_category,
)
from src.core.metrics import compute_summary_statistics
from src.core.preprocessing import apply_clahe, denoise_image
from src.core.segmentation import segment_cells
from src.utils.config_manager import get_preset, load_config
from src.utils.io_export import (
    COLOR_GREEN,
    COLOR_RED,
    COLOR_YELLOW,
    create_annotated_overlay,
    generate_csv_data,
)
from tests.generate_test_images import create_all_test_images


@pytest.fixture(scope="module")
def setup_test_images():
    """Generiert synthetische Testbilder für Integrationstests."""
    return create_all_test_images("tests/data")


def test_confidence_score_normalization_and_categories():
    """Testet die Normalisierung des Konfidenzwerts und die Ampel-Schwellenwerte."""
    # 1. Schwellenwert-Logik testen
    assert get_confidence_category(1.0) == "GREEN"
    assert get_confidence_category(0.85) == "GREEN"
    assert get_confidence_category(0.70) == "GREEN"
    assert get_confidence_category(0.699) == "YELLOW"
    assert get_confidence_category(0.55) == "YELLOW"
    assert get_confidence_category(0.40) == "YELLOW"
    assert get_confidence_category(0.399) == "RED"
    assert get_confidence_category(0.20) == "RED"
    assert get_confidence_category(0.0) == "RED"

    # Fehlerbehandlung für get_confidence_category
    with pytest.raises(TypeError):
        get_confidence_category("invalid_string")  # type: ignore

    # 2. compute_cell_confidence Normalisierung
    img = np.full((100, 100), 200, dtype=np.uint8)
    cv2.circle(img, (50, 50), 15, 30, -1)

    # Perfekt kreisförmige Zelle
    mask = np.zeros((100, 100), dtype=np.uint8)
    cv2.circle(mask, (50, 50), 15, 255, -1)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnt = contours[0]

    cell = {
        "cell_id": 1,
        "x_px": 50.0,
        "y_px": 50.0,
        "area_px": float(cv2.contourArea(cnt)),
        "contour_work": cnt,
        "mask_work": mask,
    }

    enriched = compute_cell_confidence(cell, img)

    assert "confidence" in enriched
    assert "confidence_category" in enriched
    assert "cnr" in enriched

    assert 0.0 <= enriched["confidence"] <= 1.0
    assert enriched["confidence_category"] in ("GREEN", "YELLOW", "RED")
    assert enriched["confidence_category"] == "GREEN"
    assert enriched["confidence"] >= 0.70
    assert isinstance(enriched["cnr"], float)
    assert enriched["cnr"] > 0.0


def test_confidence_penalties_on_irregular_shapes():
    """Testet, dass unregelmäßige, zerklüftete oder kontrastarme Formen Punktabzug erhalten."""
    img = np.full((200, 200), 200, dtype=np.uint8)

    # 1. Schöne kreisförmige Zelle mit hohem Kontrast
    cv2.circle(img, (50, 50), 16, 20, -1)
    mask_good = np.zeros((200, 200), dtype=np.uint8)
    cv2.circle(mask_good, (50, 50), 16, 255, -1)
    cnt_good, _ = cv2.findContours(mask_good, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    cell_good = {
        "cell_id": 1,
        "x_px": 50.0,
        "y_px": 50.0,
        "area_px": float(cv2.contourArea(cnt_good[0])),
        "contour_work": cnt_good[0],
        "mask_work": mask_good,
    }
    enriched_good = compute_cell_confidence(cell_good, img)

    # 2. Sehr unregelmäßige, gezackte Stern-Form (niedrige Zirkularität und Solidität)
    mask_bad = np.zeros((200, 200), dtype=np.uint8)
    pts = np.array(
        [
            [150, 120],
            [160, 145],
            [190, 150],
            [165, 165],
            [175, 195],
            [150, 175],
            [125, 195],
            [135, 165],
            [110, 150],
            [140, 145],
        ],
        dtype=np.int32,
    )
    cv2.fillPoly(mask_bad, [pts], 255)
    # Geringer Kontrast auf dem Bild für dieses Objekt
    cv2.fillPoly(img, [pts], 190)

    cnt_bad, _ = cv2.findContours(mask_bad, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cell_bad = {
        "cell_id": 2,
        "x_px": 150.0,
        "y_px": 150.0,
        "area_px": float(cv2.contourArea(cnt_bad[0])),
        "contour_work": cnt_bad[0],
        "mask_work": mask_bad,
    }
    enriched_bad = compute_cell_confidence(cell_bad, img)

    # Gute Zelle hat hohe Konfidenz (GREEN), unregelmäßige Zelle fällt ab (YELLOW oder RED)
    assert enriched_good["confidence"] > enriched_bad["confidence"]
    assert enriched_good["confidence_category"] == "GREEN"
    assert enriched_bad["confidence_category"] in ("YELLOW", "RED")
    assert enriched_bad["confidence"] < 0.70


def test_summary_metrics_confidence_counts():
    """Testet die korrekte Aggregation von Konfidenz-Statistiken in compute_summary_statistics."""
    cells = [
        {"cell_id": 1, "area_px": 200.0, "circularity": 0.90, "confidence": 0.88, "confidence_category": "GREEN"},
        {"cell_id": 2, "area_px": 210.0, "circularity": 0.85, "confidence": 0.75, "confidence_category": "GREEN"},
        {"cell_id": 3, "area_px": 180.0, "circularity": 0.65, "confidence": 0.58, "confidence_category": "YELLOW"},
        {"cell_id": 4, "area_px": 170.0, "circularity": 0.60, "confidence": 0.45, "confidence_category": "YELLOW"},
        {"cell_id": 5, "area_px": 150.0, "circularity": 0.35, "confidence": 0.25, "confidence_category": "RED"},
    ]

    viab_summary = {
        "total_cells": 5,
        "live_cells": 4,
        "dead_cells": 1,
        "viability_pct": 80.0,
    }

    summary = compute_summary_statistics(cells, viab_summary)

    assert summary["total_cells"] == 5
    assert summary["high_confidence_cells"] == 2
    assert summary["uncertain_cells"] == 2
    assert summary["problematic_cells"] == 1
    assert summary["mean_confidence"] == round((0.88 + 0.75 + 0.58 + 0.45 + 0.25) / 5.0, 3)

    # Test mit leerer Zellliste
    empty_summary = compute_summary_statistics([])
    assert empty_summary["total_cells"] == 0
    assert empty_summary["high_confidence_cells"] == 0
    assert empty_summary["uncertain_cells"] == 0
    assert empty_summary["problematic_cells"] == 0
    assert empty_summary["mean_confidence"] == 0.0


def test_csv_export_confidence_columns():
    """Testet, dass der CSV-Export die Spalten 'Confidence' und 'Confidence_Category' enthält."""
    cells = [
        {
            "cell_id": 1,
            "status": "LIVE",
            "confidence": 0.912,
            "confidence_category": "GREEN",
            "x_px": 102.5,
            "y_px": 88.0,
            "area_px": 250.0,
            "area_um2": 18.5,
            "circularity": 0.89,
            "solidity": 0.96,
            "i_core": 220.0,
            "i_ring": 160.0,
            "intensity_diff": 60.0,
        },
        {
            "cell_id": 2,
            "status": "DEAD",
            "confidence": 0.520,
            "confidence_category": "YELLOW",
            "x_px": 300.0,
            "y_px": 210.0,
            "area_px": 190.0,
            "area_um2": None,
            "circularity": 0.62,
            "solidity": 0.88,
            "i_core": 45.0,
            "i_ring": 180.0,
            "intensity_diff": -135.0,
        },
    ]

    csv_text = generate_csv_data(cells)
    assert isinstance(csv_text, str)

    reader = csv.reader(io.StringIO(csv_text), delimiter=";")
    rows = list(reader)

    # Header prüfen
    header = rows[0]
    assert "Confidence" in header
    assert "Confidence_Category" in header

    conf_idx = header.index("Confidence")
    cat_idx = header.index("Confidence_Category")

    # Zeilenwerte prüfen
    row1 = rows[1]
    assert float(row1[conf_idx]) == 0.912
    assert row1[cat_idx] == "GREEN"

    row2 = rows[2]
    assert float(row2[conf_idx]) == 0.520
    assert row2[cat_idx] == "YELLOW"


def test_overlay_traffic_light_drawing():
    """Testet das Zeichnen von Ampelfarben (Grün, Gelb, Rot) im annotierten Overlay."""
    h, w = 300, 400
    img = np.full((h, w), 200, dtype=np.uint8)

    cells = [
        {
            "cell_id": 1,
            "status": "LIVE",
            "confidence": 0.85,
            "confidence_category": "GREEN",
            "x_px": 80.0,
            "y_px": 80.0,
            "area_px": 200.0,
        },
        {
            "cell_id": 2,
            "status": "LIVE",
            "confidence": 0.55,
            "confidence_category": "YELLOW",
            "x_px": 180.0,
            "y_px": 150.0,
            "area_px": 180.0,
        },
        {
            "cell_id": 3,
            "status": "DEAD",
            "confidence": 0.25,
            "confidence_category": "RED",
            "x_px": 280.0,
            "y_px": 220.0,
            "area_px": 150.0,
        },
    ]

    overlay = create_annotated_overlay(img, cells, show_labels=True, show_contours=False)

    assert isinstance(overlay, np.ndarray)
    assert overlay.ndim == 3
    assert overlay.shape[2] == 3
    assert overlay.shape[:2] == (h, w)

    # Prüfe das Vorhandensein der drei Ampelfarben im gezeichneten Bild
    # COLOR_GREEN = (0, 220, 0)
    has_green = np.any(np.all(overlay == COLOR_GREEN, axis=-1))
    # COLOR_YELLOW = (0, 215, 255)
    has_yellow = np.any(np.all(overlay == COLOR_YELLOW, axis=-1))
    # COLOR_RED = (0, 0, 235)
    has_red = np.any(np.all(overlay == COLOR_RED, axis=-1))

    assert has_green, f"Grüne Farbe {COLOR_GREEN} nicht im Overlay gefunden"
    assert has_yellow, f"Gelbe Farbe {COLOR_YELLOW} nicht im Overlay gefunden"
    assert has_red, f"Rote Farbe {COLOR_RED} nicht im Overlay gefunden"


def test_segmentation_enriches_confidence_fields(setup_test_images):
    """Verifiziert, dass segment_cells alle Zellen automatisch mit Konfidenz-Feldern anreichert."""
    img_path = "tests/data/synthetic_clean_cluster.png"
    assert os.path.exists(img_path)

    img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
    config = load_config("config.yaml")
    preset = get_preset("Standard_Brightfield", config)

    clahe = apply_clahe(img)
    denoised = denoise_image(clahe)

    cells, markers, binary = segment_cells(denoised, preset["segmentation"])

    assert len(cells) >= 7
    for cell in cells:
        assert "confidence" in cell
        assert "confidence_category" in cell
        assert "cnr" in cell

        assert isinstance(cell["confidence"], float)
        assert 0.0 <= cell["confidence"] <= 1.0
        assert cell["confidence_category"] in ("GREEN", "YELLOW", "RED")
        assert isinstance(cell["cnr"], float)


def test_confidence_custom_weights_and_input_validation():
    """Testet benutzerdefinierte Gewichtungen und Fehlerbehandlung bei ungültigen Eingaben."""
    img = np.full((100, 100), 180, dtype=np.uint8)
    mask = np.zeros((100, 100), dtype=np.uint8)
    cv2.circle(mask, (50, 50), 10, 255, -1)

    cell = {
        "cell_id": 1,
        "x_px": 50.0,
        "y_px": 50.0,
        "area_px": 314.0,
        "circularity": 0.8,
        "solidity": 0.9,
        "mask_work": mask,
    }

    # Nur Zirkularität & Solidität gewichten
    enriched = compute_cell_confidence(cell.copy(), img, weights=(0.5, 0.5, 0.0))
    expected = round(0.5 * 0.8 + 0.5 * 0.9, 3)
    assert enriched["confidence"] == expected

    # Ungültige Eingaben
    with pytest.raises(TypeError):
        compute_cell_confidence("not_a_dict", img)  # type: ignore

    with pytest.raises(TypeError):
        compute_cell_confidence(cell, "not_an_array")  # type: ignore

    with pytest.raises(ValueError):
        compute_cell_confidence(cell, np.array([]))

    with pytest.raises(ValueError):
        compute_cell_confidence(cell, np.zeros((10, 10, 10, 10), dtype=np.uint8))

    with pytest.raises(ValueError):
        compute_cell_confidence(cell, img, weights=(0.5, 0.5))  # type: ignore
