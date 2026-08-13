"""Unit-Tests für das Segmentierungsmodul (Watershed & Cell Splitting)."""

import os
import cv2
import pytest
from tests.generate_test_images import create_all_test_images
from src.core.preprocessing import apply_clahe, denoise_image, to_grayscale
from src.core.segmentation import segment_cells
from src.utils.config_manager import load_config, get_preset


@pytest.fixture(scope="module")
def setup_test_images():
    """Generiert die synthetischen Testbilder für die Unit-Tests."""
    test_files = create_all_test_images("tests/data")
    return test_files


def test_segmentation_clean_cluster(setup_test_images):
    """Testet die Segmentierung und Zell-Trennung auf verclusterten Bildern."""
    img_path = "tests/data/synthetic_clean_cluster.png"
    assert os.path.exists(img_path)

    img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
    config = load_config("config.yaml")
    preset = get_preset("Standard_Brightfield", config)
    params = preset["segmentation"]

    clahe = apply_clahe(img)
    denoised = denoise_image(clahe)

    cells, markers, binary = segment_cells(denoised, params, scale_factor=1.0)

    # Es sollten ca. 7 bis 13 synthetische Zellen im Bild vorhanden sein
    assert len(cells) >= 7
    assert len(cells) <= 16

    first_cell = cells[0]
    assert "x_px" in first_cell
    assert "y_px" in first_cell
    assert "area_px" in first_cell
    assert "circularity" in first_cell
    assert first_cell["circularity"] > 0.3


def test_segmentation_vignetting_and_dust(setup_test_images):
    """Testet die Segmentierung bei Vignettierung und Staub-Artefakten."""
    vignette_path = "tests/data/synthetic_vignetting_gradient.png"
    dust_path = "tests/data/synthetic_dust_artifacts.png"

    config = load_config("config.yaml")
    preset = get_preset("Standard_Brightfield", config)
    params = preset["segmentation"]

    for path in [vignette_path, dust_path]:
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        clahe = apply_clahe(img)
        denoised = denoise_image(clahe)
        cells, _, _ = segment_cells(denoised, params)

        # Die Beleuchtungskorrektur sollte auch hier >= 7 Zellen sicher erkennen
        assert len(cells) >= 7
