"""Vorverarbeitungs-Modul für CellCounter Pro.

Führt Konvertierung in Graustufen, Downscaling für hochauflösende 20-50 Megapixel Bilder,
CLAHE-Beleuchtungskorrektur und Entrauschung durch.
"""

from typing import Tuple
import cv2
import numpy as np

from src.utils.logger import get_logger

logger = get_logger("preprocessing")


def to_grayscale(image: np.ndarray) -> np.ndarray:
    """Konvertiert ein BGR- oder RGB-Bild zuverlässig in ein 8-Bit Grauwertbild.

    Args:
        image: Eingabe-Array (Graustufen oder RGB/BGR).

    Returns:
        np.ndarray: 2D-Graustufenbild (uint8).
    """
    if image.ndim == 2:
        return image.astype(np.uint8)

    if image.ndim == 3:
        if image.shape[2] == 4:  # RGBA
            image = cv2.cvtColor(image, cv2.COLOR_RGBA2RGB)
        if image.shape[2] == 3:  # BGR/RGB
            return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    raise ValueError(f"Unerwartetes Bildformat mit Shape {image.shape}")


def downscale_image_if_needed(
    image: np.ndarray, max_dimension: int = 2048
) -> Tuple[np.ndarray, float]:
    """Skaliert große Mikroskopiebilder temporär herunter, um die Performance zu sichern.

    Args:
        image: Eingabebild (Graustufen oder RGB).
        max_dimension: Maximale zugelassene Pixel-Länge der Hauptdiagonale/Seiten.

    Returns:
        Tuple[np.ndarray, float]:
            - Skaliertes Bild (oder Originalbild, falls unter max_dimension).
            - Skalierungsfaktor (scale_factor <= 1.0).
              Um Koordinaten auf das Original umzurechnen: orig_coord = scaled_coord / scale_factor.
    """
    height, width = image.shape[:2]
    max_side = max(height, width)

    if max_side <= max_dimension or max_dimension <= 0:
        return image, 1.0

    scale_factor = float(max_dimension) / float(max_side)
    new_width = max(1, int(round(width * scale_factor)))
    new_height = max(1, int(round(height * scale_factor)))

    scaled = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_AREA)
    logger.info(f"Bild von ({width}x{height}) auf ({new_width}x{new_height}) herunterskaliert (Faktor: {scale_factor:.4f}).")
    return scaled, scale_factor


def apply_clahe(
    gray: np.ndarray,
    clip_limit: float = 2.0,
    tile_grid_size: Tuple[int, int] = (8, 8),
) -> np.ndarray:
    """Wendet adaptive Histogramm-Egalisierung (CLAHE) an, um lokale Kontraste zu schärfen.

    Args:
        gray: 2D-Graustufenbild (uint8).
        clip_limit: Kontrastbegrenzungsfaktor.
        tile_grid_size: Kachelraster-Größe (z.B. 8x8).

    Returns:
        np.ndarray: Kontrastkorrigiertes 2D-Graustufenbild.
    """
    if gray.ndim != 2:
        gray = to_grayscale(gray)

    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
    return clahe.apply(gray)


def denoise_image(gray: np.ndarray, kernel_size: int = 5) -> np.ndarray:
    """Filtert Rauschen und kleine Artefakte mittels Gauß-Filterung.

    Args:
        gray: 2D-Graustufenbild.
        kernel_size: Ungerade Kernel-Größe (z.B. 3, 5, 7).

    Returns:
        np.ndarray: Entrauschtes Bild.
    """
    if kernel_size % 2 == 0:
        kernel_size += 1

    return cv2.GaussianBlur(gray, (kernel_size, kernel_size), 0)


def remove_background_flatfield(gray: np.ndarray, radius: int = 31) -> np.ndarray:
    """Führt eine Top-Hat-Transformation zur Korrektur ungleichmäßiger Ausleuchtung durch.

    Args:
        gray: 2D-Graustufenbild.
        radius: Radius des strukturellen Elements.

    Returns:
        np.ndarray: Beleuchtungskorrigiertes Bild.
    """
    if radius % 2 == 0:
        radius += 1

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (radius, radius))
    background = cv2.morphologyEx(gray, cv2.MORPH_DILATE, kernel)
    # Subtrahiere großflächigen Hintergrund
    diff = cv2.subtract(background, gray)
    return diff
