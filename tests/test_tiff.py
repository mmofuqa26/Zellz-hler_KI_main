"""Unit-Tests für den TIFF-Handler (16-Bit & Metadaten)."""

import numpy as np
import pytest
from tests.generate_test_images import create_all_test_images
from src.core.tiff_handler import load_image_with_metadata, normalize_to_8bit


@pytest.fixture(scope="module")
def setup_test_images():
    return create_all_test_images("tests/data")


def test_normalize_16bit_to_8bit():
    """Testet die Perzentil-Normalisierung von 16-Bit-Bildern."""
    img_16bit = np.random.randint(5000, 50000, (100, 100), dtype=np.uint16)
    img_8bit = normalize_to_8bit(img_16bit)

    assert img_8bit.dtype == np.uint8
    assert img_8bit.shape == (100, 100)
    assert np.min(img_8bit) >= 0
    assert np.max(img_8bit) <= 255


def test_load_16bit_tiff_file(setup_test_images):
    """Testet das Laden einer 16-Bit-TIFF-Datei mitsamt Metadaten."""
    tiff_path = "tests/data/synthetic_16bit_microscopy.tiff"
    img_8bit, metadata = load_image_with_metadata(tiff_path, "test.tiff")

    assert img_8bit.dtype == np.uint8
    assert metadata["is_tiff"] is True
    assert metadata["original_dtype"] == "uint16"
