"""Metrik- und Statistikmodul für CellCounter Pro.

Aggregiert Zellzählungsergebnisse, berechnet statistische Verteilungen (Mittelwert, Standardabweichung),
Konfidenzmetriken (Unsichere/Problematische Zellen) und stellt Datenstrukturen für Diagramme bereit.
"""

from typing import Any, Dict, List, Optional
import numpy as np


def compute_summary_statistics(
    cell_list: List[Dict[str, Any]],
    summary_viability: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Berechnet zusammenfassende statistische Kennzahlen über alle segmentierten Zellen.

    Ermittelt Zellgesamtzahl, Lebend/Tot-Verteilung, Größenverteilung, Zirkularität
    sowie Konfidenz-Statistiken (unsichere, problematische und hochkonfidente Zellen).

    Args:
        cell_list: Liste von Einzelzelldaten (mit Schlüsseln wie 'area_px', 'circularity', 'confidence').
        summary_viability: Optionales Wörterbuch aus viability.py mit Zählwerten.

    Returns:
        Dict[str, Any]: Umfassendes Wörterbuch mit Zellzahl, Viabilität, Konfidenzen und Größenverteilungen.
    """
    total = len(cell_list)
    if total == 0:
        return {
            "total_cells": 0,
            "live_cells": 0,
            "dead_cells": 0,
            "viability_pct": 0.0,
            "mean_area_px": 0.0,
            "std_area_px": 0.0,
            "min_area_px": 0.0,
            "max_area_px": 0.0,
            "mean_circularity": 0.0,
            "mean_area_um2": None,
            "uncertain_cells": 0,
            "problematic_cells": 0,
            "high_confidence_cells": 0,
            "mean_confidence": 0.0,
        }

    if summary_viability is None:
        summary_viability = {}

    areas_px = np.array([c.get("area_px", 0.0) for c in cell_list], dtype=np.float64)
    circularities = np.array([c.get("circularity", 0.0) for c in cell_list], dtype=np.float64)
    confidences = np.array([c.get("confidence", 0.0) for c in cell_list], dtype=np.float64)

    areas_um2 = [c["area_um2"] for c in cell_list if c.get("area_um2") is not None]

    high_confidence_count = sum(
        1 for c in cell_list
        if c.get("confidence_category") == "GREEN" or c.get("confidence", 0.0) >= 0.70
    )
    uncertain_count = sum(
        1 for c in cell_list
        if c.get("confidence_category") == "YELLOW" or (0.40 <= c.get("confidence", 0.0) < 0.70)
    )
    problematic_count = sum(
        1 for c in cell_list
        if c.get("confidence_category") == "RED" or c.get("confidence", 0.0) < 0.40
    )

    metrics = {
        "total_cells": summary_viability.get("total_cells", total),
        "live_cells": summary_viability.get("live_cells", total),
        "dead_cells": summary_viability.get("dead_cells", 0),
        "viability_pct": summary_viability.get("viability_pct", 100.0),
        "mean_area_px": round(float(np.mean(areas_px)), 2),
        "std_area_px": round(float(np.std(areas_px)), 2),
        "min_area_px": round(float(np.min(areas_px)), 2),
        "max_area_px": round(float(np.max(areas_px)), 2),
        "mean_circularity": round(float(np.mean(circularities)), 3),
        "mean_area_um2": round(float(np.mean(areas_um2)), 2) if areas_um2 else None,
        "uncertain_cells": uncertain_count,
        "problematic_cells": problematic_count,
        "high_confidence_cells": high_confidence_count,
        "mean_confidence": round(float(np.mean(confidences)), 3),
    }

    return metrics
