"""TIFF-Handler für CellCounter Pro.

Verarbeitet 8-Bit/16-Bit-Mikroskopie-TIFFs, Multi-Channel-Aufnahmen und Z-Stacks.
Stellt Funktionen zur Perzentil-Normalisierung und Skalierung auf 8-Bit bereit.
"""

import os
from typing import Any, Dict, Optional, Tuple, Union
import cv2
import numpy as np
import tifffile

from src.utils.logger import get_logger

logger = get_logger("tiff_handler")


def load_image_with_metadata(
    file_source: Union[str, bytes], filename_hint: str = "image.tiff"
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Lädt ein Bild (TIFF, PNG, JPEG) und extrahiert relevante Metadaten.

    Args:
        file_source: Dateipfad (str) oder Bytes-Buffer.
        filename_hint: Hinweis zum Dateinamen zur Endungsbestimmung.

    Returns:
        Tuple[np.ndarray, Dict[str, Any]]:
            - Geladenes NumPy-Array (8-Bit BGR/Grauwert oder Multi-Slice/Channel).
            - Metadaten-Wörterbuch (Auflösung um_per_pixel, Z-Stack-Tiefe, Kanäle).
    """
    metadata: Dict[str, Any] = {
        "filename": os.path.basename(filename_hint) if isinstance(filename_hint, str) else "image",
        "is_tiff": filename_hint.lower().endswith((".tif", ".tiff")),
        "um_per_pixel": None,
        "num_channels": 1,
        "num_slices": 1,
        "original_dtype": "uint8",
    }

    if isinstance(file_source, str) and not os.path.exists(file_source):
        raise FileNotFoundError(f"Datei '{file_source}' nicht gefunden.")

    # Standard OpenCV-Leser für Nicht-TIFFs oder einfache Bilder
    if not metadata["is_tiff"]:
        if isinstance(file_source, str):
            img = cv2.imread(file_source, cv2.IMREAD_UNCHANGED)
        else:
            file_bytes = np.frombuffer(file_source, dtype=np.uint8)
            img = cv2.imdecode(file_bytes, cv2.IMREAD_UNCHANGED)

        if img is None:
            raise ValueError(f"Bild '{filename_hint}' konnte nicht decodiert werden.")

        metadata["original_dtype"] = str(img.dtype)
        img_8bit = normalize_to_8bit(img)
        return img_8bit, metadata

    # TIFF-Spezialbehandlung mit tifffile
    try:
        if isinstance(file_source, str):
            with tifffile.TiffFile(file_source) as tif:
                arr = tif.asarray()
                metadata["original_dtype"] = str(arr.dtype)
                
                # Versuche Pixelauflösung zu extrahieren
                page = tif.pages[0]
                if hasattr(page, "tags"):
                    x_res = page.tags.get("XResolution")
                    res_unit = page.tags.get("ResolutionUnit")
                    if x_res and res_unit and x_res.value[1] != 0:
                        res_val = x_res.value[0] / x_res.value[1]
                        # 2 = Inch, 3 = Centimeter
                        if res_unit.value == 3:  # cm
                            px_per_um = res_val / 10000.0
                            if px_per_um > 0:
                                metadata["um_per_pixel"] = 1.0 / px_per_um
                        elif res_unit.value == 2:  # inch
                            px_per_um = res_val / 25400.0
                            if px_per_um > 0:
                                metadata["um_per_pixel"] = 1.0 / px_per_um
        else:
            arr = tifffile.imread(file_source)
            metadata["original_dtype"] = str(arr.dtype)

        # Form-Analyse (Z-Stack / Multi-Channel)
        shape = arr.shape
        logger.info(f"TIFF geladen mit Shape {shape} und Dtype {arr.dtype}")

        if arr.ndim == 2:
            img_8bit = normalize_to_8bit(arr)
            return img_8bit, metadata
        elif arr.ndim == 3:
            # Könnte RGB (H, W, 3) oder Z-Stack (Z, H, W) oder Multi-Channel sein
            if shape[2] in (3, 4):  # RGB / RGBA
                metadata["num_channels"] = shape[2]
                img_8bit = normalize_to_8bit(arr)
                return img_8bit, metadata
            else:
                # Z-Stack: Erzeuge Max-Intensity-Projection als Standard
                metadata["num_slices"] = shape[0]
                logger.info(f"Multi-Slice TIFF erkannt ({shape[0]} Slices). Erstelle Max Intensity Projection.")
                max_proj = np.max(arr, axis=0)
                img_8bit = normalize_to_8bit(max_proj)
                return img_8bit, metadata
        elif arr.ndim == 4:
            # (Z, C, H, W) oder (Z, H, W, C)
            metadata["num_slices"] = shape[0]
            metadata["num_channels"] = shape[1]
            max_proj = np.max(arr, axis=(0, 1))
            img_8bit = normalize_to_8bit(max_proj)
            return img_8bit, metadata
        else:
            img_8bit = normalize_to_8bit(arr)
            return img_8bit, metadata

    except Exception as err:
        logger.error(f"Fehler beim Verarbeiten des TIFFs '{filename_hint}': {err}")
        # Fallback auf OpenCV
        if isinstance(file_source, str):
            img = cv2.imread(file_source, cv2.IMREAD_GRAYSCALE)
        else:
            file_bytes = np.frombuffer(file_source, dtype=np.uint8)
            img = cv2.imdecode(file_bytes, cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise ValueError(f"Bild '{filename_hint}' konnte nicht verarbeitet werden: {err}")
        return normalize_to_8bit(img), metadata


def normalize_to_8bit(
    image: np.ndarray, p_low: float = 1.0, p_high: float = 99.0
) -> np.ndarray:
    """Skaliert 16-Bit/Float-Grauwert- oder Farbbilder robust auf 8-Bit (0-255).

    Verwendet perzentil-basierte Min-Max-Skalierung, um Ausreißer und Sättigung zu vermeiden.

    Args:
        image: Eingabe-Array (uint8, uint16, float32 etc.).
        p_low: Unteres Perzentil (Standard: 1.0%).
        p_high: Oberes Perzentil (Standard: 99.0%).

    Returns:
        np.ndarray: Auf uint8 skalierte Bildmatrix (0-255).
    """
    if image.dtype == np.uint8 and p_low == 0.0 and p_high == 100.0:
        return image

    if image.ndim == 3 and image.shape[2] in (3, 4):
        # Kanalweise Normalisierung für Farbbilder
        channels = [normalize_to_8bit(image[:, :, c], p_low, p_high) for c in range(image.shape[2])]
        return np.dstack(channels)

    # Perzentilgrenzen ermitteln
    v_min, v_max = np.percentile(image, (p_low, p_high))
    if v_max <= v_min:
        v_min, v_max = float(np.min(image)), float(np.max(image))

    if v_max <= v_min:
        return np.zeros(image.shape, dtype=np.uint8)

    # Robustes Min-Max Clipping & Scaling
    clipped = np.clip(image, v_min, v_max)
    norm = ((clipped - v_min) / (v_max - v_min) * 255.0).astype(np.uint8)
    return norm
