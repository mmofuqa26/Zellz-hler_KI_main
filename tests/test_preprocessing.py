"""Unit-Tests für das Preprocessing-Modul."""

import numpy as np
import pytest

from src.core.preprocessing import (
    apply_clahe,
    denoise_image,
    downscale_image_if_needed,
    remove_background_flatfield,
    to_grayscale,
)


def test_to_grayscale_conversion():
    """Testet die Konvertierung von RGB/RGBA in Graustufen."""
    rgb = np.full((100, 100, 3), 128, dtype=np.uint8)
    gray = to_grayscale(rgb)
    assert gray.ndim == 2
    assert gray.shape == (100, 100)

    rgba = np.full((100, 100, 4), 200, dtype=np.uint8)
    gray_rgba = to_grayscale(rgba)
    assert gray_rgba.ndim == 2


def test_downscale_image_if_needed():
    """Testet das Herunterskalieren großer Mikroskopie-Bilder."""
    large_img = np.zeros((4000, 3000), dtype=np.uint8)
    scaled, scale_factor = downscale_image_if_needed(large_img, max_dimension=2000)

    assert scale_factor == 2000.0 / 4000.0
    assert scaled.shape == (2000, 1500)

    # Bild unter Limit soll nicht skaliert werden
    small_img = np.zeros((1000, 800), dtype=np.uint8)
    scaled_s, scale_s = downscale_image_if_needed(small_img, max_dimension=2000)
    assert scale_s == 1.0
    assert scaled_s.shape == (1000, 800)


def test_clahe_and_denoise():
    """Testet CLAHE-Egalisierung und Entrauschung."""
    gray = np.random.randint(50, 200, (200, 200), dtype=np.uint8)
    clahe_img = apply_clahe(gray, clip_limit=2.0)
    assert clahe_img.shape == (200, 200)

    denoised = denoise_image(clahe_img, kernel_size=5)
    assert denoised.shape == (200, 200)


def test_remove_background_flatfield():
    """Testet die Top-Hat Hintergrundkorrektur."""
    gray = np.full((100, 100), 150, dtype=np.uint8)
    corr = remove_background_flatfield(gray, radius=21)
    assert corr.shape == (100, 100)
