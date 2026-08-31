"""Konfidenzbewertungs-Modul für CellCounter Pro (R2).

Berechnet für jede segmentierte Zelle einen normalisierten Konfidenz-Score (0.0 bis 1.0)
basierend auf Zirkularität, Solidität und lokalem Kontrast-zu-Rauschen-Verhältnis (CNR).
Kategorisiert Zellen nach dem Ampel-Schema: GRÜN (sicher), GELB (unsicher), ROT (problematisch).
"""

import math
from typing import Any, Dict, Optional, Tuple
import cv2
import numpy as np

from src.core.preprocessing import to_grayscale
from src.utils.logger import get_logger

logger = get_logger("confidence")

# Standard-Grenzwerte für die Konfidenz-Kategorisierung
THRESHOLD_HIGH_CONFIDENCE = 0.70
THRESHOLD_LOW_CONFIDENCE = 0.40


def get_confidence_category(confidence: float) -> str:
    """Bestimmt die Ampel-Kategorie ('GREEN', 'YELLOW', 'RED') basierend auf dem Konfidenzwert.

    Grenzwerte:
        - 'GREEN': confidence >= 0.70
        - 'YELLOW': 0.40 <= confidence < 0.70
        - 'RED': confidence < 0.40

    Args:
        confidence: Normalisierter Konfidenzwert im Bereich [0.0, 1.0].

    Returns:
        str: 'GREEN', 'YELLOW' oder 'RED'.

    Raises:
        TypeError: Wenn confidence kein int oder float ist.
    """
    if not isinstance(confidence, (int, float)):
        raise TypeError(f"Erwartet int oder float, erhalten: {type(confidence).__name__}")

    if confidence >= THRESHOLD_HIGH_CONFIDENCE:
        return "GREEN"
    elif confidence >= THRESHOLD_LOW_CONFIDENCE:
        return "YELLOW"
    else:
        return "RED"


def compute_cell_confidence(
    cell: Dict[str, Any],
    gray_work: np.ndarray,
    weights: Optional[Tuple[float, float, float]] = (0.35, 0.35, 0.30),
) -> Dict[str, Any]:
    """Berechnet den Konfidenz-Score und die Ampel-Kategorie für eine segmentierte Zelle.

    Kombiniert Zirkularität (C = 4*pi*A / P^2), Solidität (S = A / A_ConvexHull) und das
    lokale Kontrast-zu-Rauschen-Verhältnis (S_CNR aus Kern- zu Ring-Intensität).

    S_conf = w_c * C + w_s * S + w_cnr * S_CNR, geklemmt auf [0.0, 1.0].

    Args:
        cell: Wörterbuch mit Einzelzelldaten (u. a. 'contour_work', 'mask_work' oder 'circularity', 'solidity').
        gray_work: 2D-Graustufenbild in Arbeitsauflösung.
        weights: Tupel (Gewicht_Zirkularität, Gewicht_Solidität, Gewicht_CNR). Standard: (0.35, 0.35, 0.30).

    Returns:
        Dict[str, Any]: Das aktualisierte Zell-Wörterbuch mit den Schlüsseln:
            - 'confidence': float in [0.0, 1.0] (gerundet auf 3 Nachkommastellen)
            - 'confidence_category': 'GREEN' | 'YELLOW' | 'RED'
            - 'cnr': float (lokales Kontrast-zu-Rauschen-Verhältnis)

    Raises:
        TypeError: Wenn cell kein dict oder gray_work kein np.ndarray ist.
        ValueError: Wenn gray_work leer ist oder ungültige Dimensionen besitzt.
    """
    if not isinstance(cell, dict):
        raise TypeError(f"Erwartet Dict für cell, erhalten: {type(cell).__name__}")

    if not isinstance(gray_work, np.ndarray):
        raise TypeError(f"Erwartet np.ndarray für gray_work, erhalten: {type(gray_work).__name__}")

    if gray_work.size == 0:
        raise ValueError("Eingabebild gray_work ist leer (size == 0).")

    if gray_work.ndim == 3:
        gray_work = to_grayscale(gray_work)
    elif gray_work.ndim != 2:
        raise ValueError(f"Ungültige Bilddimensionen für gray_work: {gray_work.shape}")

    if weights is None:
        weights = (0.35, 0.35, 0.30)
    elif len(weights) != 3:
        raise ValueError(f"weights muss ein 3-Tupel sein, erhalten Länge {len(weights)}")

    w_circ, w_solid, w_cnr = float(weights[0]), float(weights[1]), float(weights[2])

    # 1. Zirkularität C ermitteln
    if "contour_work" in cell and cell["contour_work"] is not None and len(cell["contour_work"]) > 0:
        cnt = cell["contour_work"]
        area_px = float(cv2.contourArea(cnt))
        perimeter = float(cv2.arcLength(cnt, True))
        if perimeter > 0 and area_px > 0:
            c_val = (4.0 * math.pi * area_px) / (perimeter * perimeter)
        else:
            c_val = 0.0
    elif "circularity" in cell and cell["circularity"] is not None:
        c_val = float(cell["circularity"])
    else:
        c_val = 0.0

    circularity = float(np.clip(c_val, 0.0, 1.0))

    # 2. Solidität S ermitteln
    if "contour_work" in cell and cell["contour_work"] is not None and len(cell["contour_work"]) > 0:
        cnt = cell["contour_work"]
        area_px = float(cv2.contourArea(cnt))
        hull = cv2.convexHull(cnt)
        hull_area = float(cv2.contourArea(hull))
        if hull_area > 0 and area_px > 0:
            s_val = area_px / hull_area
        else:
            s_val = 0.0
    elif "solidity" in cell and cell["solidity"] is not None:
        s_val = float(cell["solidity"])
    else:
        s_val = 0.0

    solidity = float(np.clip(s_val, 0.0, 1.0))

    # 3. Lokales Kontrast-zu-Rauschen-Verhältnis (CNR)
    if "mask_work" in cell and cell["mask_work"] is not None and isinstance(cell["mask_work"], np.ndarray):
        mask_work = cell["mask_work"]
    elif "contour_work" in cell and cell["contour_work"] is not None and len(cell["contour_work"]) > 0:
        mask_work = np.zeros_like(gray_work, dtype=np.uint8)
        cv2.drawContours(mask_work, [cell["contour_work"]], -1, 255, -1)
    else:
        mask_work = np.zeros_like(gray_work, dtype=np.uint8)
        cx = int(round(cell.get("x_work", cell.get("x_px", 0.0))))
        cy = int(round(cell.get("y_work", cell.get("y_px", 0.0))))
        area_val = float(cell.get("area_px", 25.0))
        radius = max(2, int(math.sqrt(max(1.0, area_val) / math.pi)))
        cv2.circle(mask_work, (cx, cy), radius, 255, -1)

    # Kern-Maske (leicht erodiert)
    core_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    core_mask = cv2.erode(mask_work, core_kernel, iterations=1)
    if np.count_nonzero(core_mask) == 0:
        core_mask = mask_work

    # Umgebender Hintergrund-Ring
    ring_width = 4
    ring_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (ring_width * 2 + 1, ring_width * 2 + 1)
    )
    dilated_mask = cv2.dilate(mask_work, ring_kernel, iterations=1)
    ring_mask = cv2.subtract(dilated_mask, mask_work)

    core_pixels = gray_work[core_mask > 0]
    ring_pixels = gray_work[ring_mask > 0]

    if len(core_pixels) == 0 or len(ring_pixels) == 0:
        raw_cnr = 0.0
        s_cnr = 0.0
    else:
        mean_core = float(np.mean(core_pixels))
        mean_ring = float(np.mean(ring_pixels))
        std_ring = float(np.std(ring_pixels))

        contrast = abs(mean_core - mean_ring)
        noise = max(std_ring, 1.0)
        raw_cnr = contrast / noise
        # Normalisierung: CNR >= 2.5 entspricht maximaler Kontrastsicherheit 1.0
        s_cnr = float(np.clip(raw_cnr / 2.5, 0.0, 1.0))

    # 4. Zusammengesetzter Konfidenzwert
    s_conf = w_circ * circularity + w_solid * solidity + w_cnr * s_cnr
    s_conf_clamped = float(np.clip(s_conf, 0.0, 1.0))
    rounded_conf = round(s_conf_clamped, 3)

    category = get_confidence_category(rounded_conf)

    cell["confidence"] = rounded_conf
    cell["confidence_category"] = category
    cell["cnr"] = round(float(raw_cnr), 3)

    return cell
