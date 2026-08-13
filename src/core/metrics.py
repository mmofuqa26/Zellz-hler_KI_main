"""Metrik- und Statistikmodul für CellCounter Pro.

Aggregiert Zellzählungsergebnisse, berechnet statistische Verteilungen (Mittelwert, Standardabweichung)
und stellt Datenstrukturen für Diagramme und Berichte bereit.
"""

from typing import Any, Dict, List
import numpy as np


def compute_summary_statistics(
    cell_list: List[Dict[str, Any]], summary_viability: Dict[str, Any]
) -> Dict[str, Any]:
    """Berechnet zusammenfassende statistische Kennzahlen über alle segmentierten Zellen.

    Args:
        cell_list: Liste von Einzelzelldaten.
        summary_viability: Wörterbuch aus viability.py mit Zählwerten.

    Returns:
        Dict[str, Any]: Umfassendes Wörterbuch mit Zellzahl, Viabilität und Größenverteilungen.
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
        }

    areas_px = np.array([c["area_px"] for c in cell_list], dtype=np.float64)
    circularities = np.array([c["circularity"] for c in cell_list], dtype=np.float64)

    areas_um2 = [c["area_um2"] for c in cell_list if c.get("area_um2") is not None]

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
    }

    return metrics
