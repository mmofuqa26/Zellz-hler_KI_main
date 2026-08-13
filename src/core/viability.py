"""Viabilitäts-Modul für CellCounter Pro (Lebend/Tot-Klassifizierung).

Nutzt das Prinzip der LOKALEN HINTERGRUND-SUBTRAKTION (I_core vs. I_ring),
um unabhängig von Vignettierung, Randabstrahlungen und Mikroskopschatten
zu bestimmen, ob eine Zelle lebend oder tot (Farbstoffaufnahme) ist.
"""

from typing import Any, Dict, List, Tuple
import cv2
import numpy as np

from src.utils.logger import get_logger

logger = get_logger("viability")


def classify_viability(
    gray_work: np.ndarray,
    cell_list: List[Dict[str, Any]],
    viability_params: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Klassifiziert jede segmentierte Zelle in 'LIVE' oder 'DEAD'.

    Args:
        gray_work: 2D-Graustufenbild in Arbeitsauflösung.
        cell_list: Liste von Wörterbüchern segmentierter Zellen aus segmentation.py.
        viability_params: Wörterbuch mit Parametern (enabled, ring_width_px, intensity_diff_threshold).

    Returns:
        Tuple[List[Dict[str, Any]], Dict[str, Any]]:
            - Aktualisierte Zell-Liste mit den Keys 'status', 'i_core', 'i_ring', 'intensity_diff'.
            - Zusammenfassungs-Wörterbuch (total_cells, live_cells, dead_cells, viability_pct).
    """
    enabled = viability_params.get("enabled", True)
    ring_width = viability_params.get("ring_width_px", 4)
    threshold_diff = viability_params.get("intensity_diff_threshold", -12.0)

    total_count = len(cell_list)

    if not enabled or total_count == 0:
        for cell in cell_list:
            cell["status"] = "LIVE"
            cell["i_core"] = 0.0
            cell["i_ring"] = 0.0
            cell["intensity_diff"] = 0.0

        summary = {
            "total_cells": total_count,
            "live_cells": total_count,
            "dead_cells": 0,
            "viability_pct": 100.0 if total_count > 0 else 0.0,
        }
        return cell_list, summary

    live_count = 0
    dead_count = 0

    ring_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (ring_width * 2 + 1, ring_width * 2 + 1)
    )

    for cell in cell_list:
        mask_work = cell["mask_work"]

        # 1. Zellkern-Maske (leicht erodiert, um Ränder auszuschließen)
        core_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        core_mask = cv2.erode(mask_work, core_kernel, iterations=1)
        if np.count_nonzero(core_mask) == 0:
            core_mask = mask_work  # Fallback für sehr kleine Zellen

        # 2. Lokaler Hintergrundring um die Zelle
        dilated_mask = cv2.dilate(mask_work, ring_kernel, iterations=1)
        ring_mask = cv2.subtract(dilated_mask, mask_work)

        # 3. Mittlere Intensitäten berechnen
        i_core = float(cv2.mean(gray_work, mask=core_mask)[0])
        i_ring = float(cv2.mean(gray_work, mask=ring_mask)[0])

        intensity_diff = i_core - i_ring

        # Bei Trypanblau ist der Kern toter Zellen dunkel -> i_core < i_ring -> intensity_diff stark negativ
        if intensity_diff <= threshold_diff:
            status = "DEAD"
            dead_count += 1
        else:
            status = "LIVE"
            live_count += 1

        cell["status"] = status
        cell["i_core"] = round(i_core, 2)
        cell["i_ring"] = round(i_ring, 2)
        cell["intensity_diff"] = round(intensity_diff, 2)

    viability_pct = (live_count / total_count * 100.0) if total_count > 0 else 0.0

    summary = {
        "total_cells": total_count,
        "live_cells": live_count,
        "dead_cells": dead_count,
        "viability_pct": round(viability_pct, 2),
    }

    logger.info(f"Viabilitäts-Analyse abgeschlossen: {live_count} Lebend, {dead_count} Tot ({viability_pct:.1f}% Viabilität).")
    return cell_list, summary
