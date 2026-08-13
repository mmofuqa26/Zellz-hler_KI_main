"""Segmentierungs-Modul für CellCounter Pro (Marker-basierter Watershed mit Lokaler-Maxima-Erkennung).

Verwendet euklidische Distanz-Transformation und Lokale-Maxima-Peak-Detektion zur präzisen
Entkopplung und Zählung dicht berührender Zellen im Wasser-Scheiden-Verfahren.
"""

import math
from typing import Any, Dict, List, Tuple
import cv2
import numpy as np

from src.utils.logger import get_logger

logger = get_logger("segmentation")


def fill_binary_holes(binary: np.ndarray) -> np.ndarray:
    """Füllt innere Lücken und Hohlräume in binären Zellumrissen."""
    filled = binary.copy()
    contours, hierarchy = cv2.findContours(
        filled, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE
    )
    if contours is None or hierarchy is None:
        return filled

    for i in range(len(contours)):
        cv2.drawContours(filled, contours, i, 255, -1)

    return filled


def find_local_peaks(
    dist_transform: np.ndarray,
    min_distance_px: int = 7,
    threshold_ratio: float = 0.20,
) -> np.ndarray:
    """Findet lokales Maxima (Peaks) in der Distanzkarte zur zellulären Zentrenlokalisierung.

    Nutzt dilations-basierte Nicht-Maximum-Unterdrückung für blitzschnelle Zentrenfindung
    bei berührenden/verclusterten Zellen.
    """
    if min_distance_px % 2 == 0:
        min_distance_px += 1

    kernel = np.ones((min_distance_px, min_distance_px), dtype=np.uint8)
    dilated = cv2.dilate(dist_transform, kernel)

    # Lokale Maxima sind Punkte, die dem Maximum in ihrer Nachbarschaft entsprechen
    max_val = dist_transform.max()
    if max_val <= 0:
        return np.zeros_like(dist_transform, dtype=np.uint8)

    min_threshold = threshold_ratio * max_val
    local_peaks = (dist_transform == dilated) & (dist_transform >= min_threshold) & (dist_transform > 1.0)

    return local_peaks.astype(np.uint8) * 255


def segment_cells(
    gray: np.ndarray,
    params: Dict[str, Any],
    scale_factor: float = 1.0,
    um_per_pixel: float = None,
) -> Tuple[List[Dict[str, Any]], np.ndarray, np.ndarray]:
    """Segmentiert Zellen in einem Graustufenbild mittels Marker-basiertem Watershed.

    Args:
        gray: 2D-Graustufenbild (uint8).
        params: Wörterbuch mit Segmentierungsparametern.
        scale_factor: Skalierungsfaktor des analysierten Bildes relativ zum Original (<= 1.0).
        um_per_pixel: Optionaler Umrechnungsfaktor Mikrometer pro Pixel.

    Returns:
        Tuple[List[Dict[str, Any]], np.ndarray, np.ndarray]:
            - Liste von Einzelzelldaten.
            - Watershed-Labelmatrix (int32).
            - Binärmaske des Vordergrunds (uint8).
    """
    min_diam = params.get("min_cell_diameter_px", 10)
    max_diam = params.get("max_cell_diameter_px", 150)
    block_size = params.get("adaptive_thresh_block_size", 21)
    param_c = params.get("adaptive_thresh_c", 5)
    min_marker_area = params.get("min_marker_area_px", 2)
    dist_ratio = params.get("dist_threshold_ratio", 0.20)
    min_circularity = params.get("min_circularity", 0.20)
    min_solidity = params.get("min_solidity", 0.35)

    work_min_diam = max(2.5, min_diam * scale_factor)
    work_max_diam = max_diam * scale_factor
    work_min_area = math.pi * (work_min_diam / 2.0) ** 2
    work_max_area = math.pi * (work_max_diam / 2.0) ** 2

    # 1. Adaptives Schwellenwertverfahren + Otsu-Kombination
    if block_size % 2 == 0:
        block_size += 1

    binary_inv = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        block_size,
        param_c,
    )

    # Zusätzlicher Otsu-Check zur Unterdrückung von flächigem Rauschen
    _, otsu_inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    combined_binary = cv2.bitwise_and(binary_inv, otsu_inv)

    # Falls Otsu zu aggressiv war, nutze adaptiveThreshold
    if np.count_nonzero(combined_binary) < 0.1 * np.count_nonzero(binary_inv):
        combined_binary = binary_inv

    # 2. Morphologische Schließung & Hole-Filling
    kernel_small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    closed = cv2.morphologyEx(combined_binary, cv2.MORPH_CLOSE, kernel_small, iterations=2)
    filled = fill_binary_holes(closed)

    # 3. Morphologisches Öffnen
    opening = cv2.morphologyEx(filled, cv2.MORPH_OPEN, kernel_small, iterations=1)

    # 4. Sicheren Hintergrund bestimmen
    kernel_bg = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    sure_bg = cv2.dilate(opening, kernel_bg, iterations=2)

    # 5. Euklidische Distanztransformation
    dist_transform = cv2.distanceTransform(opening, cv2.DIST_L2, 5)

    if dist_transform.max() <= 0:
        logger.warning("Keine Objekte in der Distanztransformation gefunden.")
        return [], np.zeros_like(gray, dtype=np.int32), opening

    # 6. Lokale-Maxima-Detektion für Zellkerne (Cluster-Splitting)
    peak_kernel_size = max(3, int(round(work_min_diam * 0.6)))
    sure_fg_raw = find_local_peaks(
        dist_transform,
        min_distance_px=peak_kernel_size,
        threshold_ratio=dist_ratio,
    )

    # 7. Marker-Filterung via connectedComponents
    num_labels_raw, labels_raw, stats_raw, _ = cv2.connectedComponentsWithStats(
        sure_fg_raw
    )

    filtered_seeds = np.zeros_like(sure_fg_raw, dtype=np.uint8)
    valid_marker_count = 0

    for label_idx in range(1, num_labels_raw):
        area = stats_raw[label_idx, cv2.CC_STAT_AREA]
        if area >= min_marker_area:
            filtered_seeds[labels_raw == label_idx] = 255
            valid_marker_count += 1

    # Falls lokale Maxima zu restriktiv waren, Fallback auf Schwellenwert-Seeds
    if valid_marker_count == 0:
        _, fallback_seeds = cv2.threshold(
            dist_transform, 0.25 * dist_transform.max(), 255, cv2.THRESH_BINARY
        )
        filtered_seeds = fallback_seeds.astype(np.uint8)
        num_labels_raw, _, _, _ = cv2.connectedComponentsWithStats(filtered_seeds)
        valid_marker_count = num_labels_raw - 1

    _, markers = cv2.connectedComponents(filtered_seeds)
    markers = markers + 1  # Hintergrund = 1

    unknown = cv2.subtract(sure_bg, filtered_seeds)
    markers[unknown == 255] = 0

    # 8. Watershed-Transformation ausführen
    color_img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    cv2.watershed(color_img, markers)

    # 9. Extraktion der Segmentierungsergebnisse
    cell_list: List[Dict[str, Any]] = []
    unique_labels = np.unique(markers)

    cell_counter = 1
    for label in unique_labels:
        if label <= 1 or label == -1:
            continue

        cell_mask = np.zeros_like(gray, dtype=np.uint8)
        cell_mask[markers == label] = 255

        contours, _ = cv2.findContours(
            cell_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        if not contours:
            continue

        cnt = max(contours, key=cv2.contourArea)
        area_px_work = float(cv2.contourArea(cnt))

        if area_px_work < work_min_area or area_px_work > work_max_area:
            continue

        perimeter = cv2.arcLength(cnt, True)
        if perimeter <= 0:
            continue

        circularity = (4.0 * math.pi * area_px_work) / (perimeter * perimeter)
        circularity = min(1.0, max(0.0, circularity))

        hull = cv2.convexHull(cnt)
        hull_area = cv2.contourArea(hull)
        solidity = (area_px_work / hull_area) if hull_area > 0 else 0.0

        if circularity < min_circularity or solidity < min_solidity:
            continue

        moments = cv2.moments(cnt)
        if moments["m00"] != 0:
            cx_work = moments["m10"] / moments["m00"]
            cy_work = moments["m01"] / moments["m00"]
        else:
            x, y, w, h = cv2.boundingRect(cnt)
            cx_work, cy_work = x + w / 2.0, y + h / 2.0

        cx_orig = float(cx_work / scale_factor)
        cy_orig = float(cy_work / scale_factor)
        area_px_orig = float(area_px_work / (scale_factor * scale_factor))

        cnt_orig = (cnt.astype(np.float32) / scale_factor).astype(np.int32)

        area_um2 = None
        if um_per_pixel and um_per_pixel > 0:
            area_um2 = area_px_orig * (um_per_pixel * um_per_pixel)

        cell_data = {
            "cell_id": cell_counter,
            "label": int(label),
            "x_px": round(cx_orig, 2),
            "y_px": round(cy_orig, 2),
            "x_work": round(cx_work, 2),
            "y_work": round(cy_work, 2),
            "area_px": round(area_px_orig, 2),
            "area_um2": round(area_um2, 2) if area_um2 else None,
            "circularity": round(circularity, 3),
            "solidity": round(solidity, 3),
            "contour_orig": cnt_orig,
            "contour_work": cnt,
            "mask_work": cell_mask,
        }

        cell_list.append(cell_data)
        cell_counter += 1

    logger.info(f"Segmentierung abgeschlossen: {len(cell_list)} valide Zellen extrahiert.")
    return cell_list, markers, opening
