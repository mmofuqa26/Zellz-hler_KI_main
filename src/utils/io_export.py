"""Export-Modul für CellCounter Pro.

Erzeugt strukturierte CSV-Exporte der Zellmessungen und generiert hochaufgelöste
annotierte Übersichtsbilder (Grün = Lebend, Rot = Tot, Zell-IDs).
"""

import csv
import io
from typing import Any, Dict, List, Optional
import cv2
import numpy as np

from src.utils.logger import get_logger

logger = get_logger("io_export")


def generate_csv_data(cell_list: List[Dict[str, Any]]) -> str:
    """Generiert einen CSV-String mit allen Einzelzell-Messergebnissen.

    Args:
        cell_list: Liste aller segmentierten und klassifizierten Zellen.

    Returns:
        str: CSV-formatiertes Textdokument.
    """
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")

    # Header schreiben
    writer.writerow(
        [
            "Cell_ID",
            "Status",
            "X_px",
            "Y_px",
            "Area_px",
            "Area_um2",
            "Circularity",
            "Solidity",
            "I_Core",
            "I_Ring",
            "Intensity_Diff",
        ]
    )

    for c in cell_list:
        writer.writerow(
            [
                c.get("cell_id", ""),
                c.get("status", "UNKNOWN"),
                c.get("x_px", 0.0),
                c.get("y_px", 0.0),
                c.get("area_px", 0.0),
                c.get("area_um2", "") if c.get("area_um2") is not None else "",
                c.get("circularity", 0.0),
                c.get("solidity", 0.0),
                c.get("i_core", 0.0),
                c.get("i_ring", 0.0),
                c.get("intensity_diff", 0.0),
            ]
        )

    return output.getvalue()


def create_annotated_overlay(
    img_orig: np.ndarray,
    cell_list: List[Dict[str, Any]],
    show_labels: bool = True,
    show_contours: bool = True,
) -> np.ndarray:
    """Zeichnet ein hochauflösendes Overlay-Bild mit farbigen Zellgrenzen und Status-Markern.

    - Grün: Lebende Zelle (Farbstoffausschluss)
    - Rot: Tote Zelle (Trypanblau-Aufnahme)

    Args:
        img_orig: Originalbild in voller Auflösung (8-Bit Grauwert oder BGR/RGB).
        cell_list: Liste der segmentierten Zellen mit Konturen auf Originalkoordinaten.
        show_labels: Wenn True, werden Zell-ID Nummern eingezeichnet.
        show_contours: Wenn True, werden exakte Zellgrenzen gezeichnet.

    Returns:
        np.ndarray: Annotiertes BGR-Bild.
    """
    if img_orig.ndim == 2:
        annotated = cv2.cvtColor(img_orig, cv2.COLOR_GRAY2BGR)
    else:
        annotated = img_orig.copy()

    # Farben (BGR Format)
    COLOR_LIVE = (0, 220, 0)     # Helles Grün
    COLOR_DEAD = (0, 0, 235)     # Kräftiges Rot
    COLOR_TEXT = (255, 255, 255) # Weiß

    h, w = annotated.shape[:2]
    font_scale = max(0.4, min(1.2, max(w, h) / 2500.0))
    thickness = max(1, int(round(max(w, h) / 1500.0)))

    for cell in cell_list:
        status = cell.get("status", "LIVE")
        color = COLOR_LIVE if status == "LIVE" else COLOR_DEAD

        cx = int(round(cell["x_px"]))
        cy = int(round(cell["y_px"]))

        # Exakte Kontur auf Originalbild zeichnen
        if show_contours and "contour_orig" in cell:
            cnt = cell["contour_orig"]
            cv2.drawContours(annotated, [cnt], -1, color, thickness)
        else:
            # Kreisförmiger Marker als Fallback
            radius = max(4, int(math.sqrt(cell["area_px"] / math.pi)))
            cv2.circle(annotated, (cx, cy), radius, color, thickness)

        # Zell-Zentrumspunkt
        cv2.circle(annotated, (cx, cy), max(2, thickness), color, -1)

        # Nummerierungs-Label
        if show_labels:
            label_str = str(cell["cell_id"])
            text_size, _ = cv2.getTextSize(label_str, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
            tx = cx + 5
            ty = cy - 5

            # Text-Hintergrund für gute Lesbarkeit
            cv2.rectangle(
                annotated,
                (tx - 1, ty - text_size[1] - 2),
                (tx + text_size[0] + 2, ty + 2),
                (0, 0, 0),
                -1,
            )
            cv2.putText(
                annotated,
                label_str,
                (tx, ty),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                COLOR_TEXT,
                thickness,
                cv2.LINE_AA,
            )

    return annotated
