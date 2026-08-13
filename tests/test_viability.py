"""Unit-Tests für das Viabilitätsmodul (Lebend/Tot-Unterscheidung)."""

import cv2
import pytest
from tests.generate_test_images import create_all_test_images
from src.core.preprocessing import apply_clahe, denoise_image
from src.core.segmentation import segment_cells
from src.core.viability import classify_viability
from src.utils.config_manager import get_preset, load_config


@pytest.fixture(scope="module")
def setup_test_images():
    return create_all_test_images("tests/data")


def test_viability_classification(setup_test_images):
    """Testet die Lebend/Tot-Klassifizierung via lokaler Hintergrundsubtraktion."""
    img_path = "tests/data/synthetic_clean_cluster.png"
    gray = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)

    config = load_config("config.yaml")
    preset = get_preset("Standard_Brightfield", config)

    clahe = apply_clahe(gray)
    denoised = denoise_image(clahe)

    cells, _, _ = segment_cells(denoised, preset["segmentation"])
    cells_classified, summary = classify_viability(
        denoised, cells, preset["viability"]
    )

    assert summary["total_cells"] == len(cells_classified)
    assert summary["live_cells"] > 0
    assert summary["dead_cells"] > 0
    assert summary["viability_pct"] > 0.0 and summary["viability_pct"] < 100.0

    statuses = [c["status"] for c in cells_classified]
    assert "LIVE" in statuses
    assert "DEAD" in statuses
