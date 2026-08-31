"""Export-Modul für CellCounter Pro.

Erzeugt strukturierte CSV-Exporte der Zellmessungen (inkl. Konfidenzbewertung) und
generiert hochaufgelöste annotierte Übersichtsbilder im Ampelschema
(Grün = Sicher >= 0.70, Gelb = Unsicher 0.40-0.70, Rot = Problematisch < 0.40).
"""

import csv
from datetime import datetime
import io
import json
import math
import os
from typing import Any, Dict, List, Optional
import cv2
import numpy as np

from src.utils.logger import get_logger

logger = get_logger("io_export")

# Ampel-Farben (BGR-Format)
COLOR_GREEN = (0, 220, 0)     # Grün: Sicher (>= 0.70)
COLOR_YELLOW = (0, 215, 255)   # Gelb: Unsicher (0.40 - 0.70)
COLOR_RED = (0, 0, 235)       # Rot: Problematisch (< 0.40)
COLOR_TEXT = (255, 255, 255)   # Weiß


def generate_csv_data(cell_list: List[Dict[str, Any]]) -> str:
    """Generiert einen CSV-String mit allen Einzelzell-Messergebnissen inkl. Konfidenz-Werten.

    Args:
        cell_list: Liste aller segmentierten und klassifizierten Zellen.

    Returns:
        str: Semikolon-getrenntes CSV-formatiertes Textdokument.
    """
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")

    # Header schreiben mit Confidence und Confidence_Category
    writer.writerow(
        [
            "Cell_ID",
            "Status",
            "Confidence",
            "Confidence_Category",
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
                c.get("confidence", 0.0),
                c.get("confidence_category", "UNKNOWN"),
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
    image: np.ndarray,
    cell_list: List[Dict[str, Any]],
    show_labels: bool = True,
    show_contours: bool = True,
    scale_factor: float = 1.0,
) -> np.ndarray:
    """Zeichnet ein hochauflösendes Overlay-Bild mit Ampelfarben basierend auf dem Konfidenzwert.

    Ampel-Farben (BGR):
        - Grün: (0, 220, 0)   -> Sicher (Konfidenz >= 0.70)
        - Gelb: (0, 215, 255) -> Unsicher (0.40 <= Konfidenz < 0.70)
        - Rot:  (0, 0, 235)   -> Problematisch (Konfidenz < 0.40)

    Args:
        image: Originalbild in voller Auflösung (8-Bit Grauwert oder BGR/RGB).
        cell_list: Liste der segmentierten Zellen mit Konturen auf Originalkoordinaten.
        show_labels: Wenn True, werden Zell-ID Nummern eingezeichnet.
        show_contours: Wenn True, werden exakte Zellgrenzen gezeichnet.
        scale_factor: Optionaler Skalierungsfaktor.

    Returns:
        np.ndarray: Annotiertes BGR-Bild.
    """
    if image.ndim == 2:
        annotated = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    else:
        annotated = image.copy()

    h, w = annotated.shape[:2]
    font_scale = max(0.4, min(1.2, max(w, h) / 2500.0))
    thickness = max(1, int(round(max(w, h) / 1500.0)))

    for cell in cell_list:
        category = cell.get("confidence_category")
        if category == "GREEN":
            color = COLOR_GREEN
        elif category == "YELLOW":
            color = COLOR_YELLOW
        elif category == "RED":
            color = COLOR_RED
        else:
            conf = cell.get("confidence")
            if conf is not None:
                if conf >= 0.70:
                    color = COLOR_GREEN
                elif conf >= 0.40:
                    color = COLOR_YELLOW
                else:
                    color = COLOR_RED
            else:
                status = cell.get("status", "LIVE")
                color = COLOR_GREEN if status == "LIVE" else COLOR_RED

        cx = int(round(cell["x_px"]))
        cy = int(round(cell["y_px"]))

        # Exakte Kontur auf Originalbild zeichnen
        if show_contours and "contour_orig" in cell and cell["contour_orig"] is not None:
            cnt = cell["contour_orig"]
            cv2.drawContours(annotated, [cnt], -1, color, thickness)
        else:
            # Kreisförmiger Marker als Fallback
            area_val = float(cell.get("area_px", 25.0))
            radius = max(4, int(math.sqrt(max(1.0, area_val) / math.pi)))
            cv2.circle(annotated, (cx, cy), radius, color, thickness)

        # Zell-Zentrumspunkt
        cv2.circle(annotated, (cx, cy), max(2, thickness), color, -1)

        # Nummerierungs-Label
        if show_labels:
            label_str = str(cell.get("cell_id", ""))
            text_size, _ = cv2.getTextSize(
                label_str, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
            )
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


class _NumpySafeJSONEncoder(json.JSONEncoder):
    """JSON-Encoder zur Konvertierung von NumPy-Datentypen in Standard-Python-Typen."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, (np.integer, int)):
            return int(obj)
        if isinstance(obj, (np.floating, float)):
            return float(obj)
        if isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def save_manual_correction(
    filename: str,
    original_count: int,
    corrected_count: int,
    cell_list: List[Dict[str, Any]],
    image_path: str = "",
    output_dir: str = "data/corrections",
) -> str:
    """Speichert eine manuelle Zählkorrektur als JSON-Datei.

    Sichert den Korrekturdatensatz inklusive Zellmarkern, Konfidenzen,
    Korrektur-Delta und Zeitstempel für spätere Modell-Optimierungen.
    Erstellt das Zielverzeichnis automatisch, falls es noch nicht existiert.

    Args:
        filename: Name oder Pfad der Bilddatei (z.B. 'sample_01.png').
        original_count: Vom Algorithmus ermittelte Zellanzahl.
        corrected_count: Vom Benutzer korrigierte Gesamtzahl.
        cell_list: Liste der erkannten Zellen mit Koordinaten und Attributen.
        image_path: Optionaler Dateipfad zum referenzierten Bild. Standard: "".
        output_dir: Zielverzeichnis für die JSON-Datei. Standard: "data/corrections".

    Returns:
        str: Dateipfad zur erstellten JSON-Korrekturdatei.

    Raises:
        ValueError: Bei ungültigen Zählwerten oder Parametern.
        OSError: Bei Dateisystem- oder Schreibfehlern.
    """
    if not isinstance(filename, str) or not filename.strip():
        clean_filename = "correction"
    else:
        base_name = os.path.basename(filename.strip())
        clean_stem = os.path.splitext(base_name)[0]
        clean_filename = clean_stem if clean_stem else "correction"

    try:
        orig_cnt = int(original_count)
        corr_cnt = int(corrected_count)
    except (TypeError, ValueError) as err:
        raise ValueError(
            f"original_count und corrected_count müssen ganzzahlig sein: {err}"
        ) from err

    delta = int(corr_cnt - orig_cnt)

    now = datetime.now()
    timestamp_iso = now.isoformat()
    timestamp_prefix = now.strftime("%Y%m%d_%H%M%S")

    # Ausgabeverzeichnis sicherstellen
    os.makedirs(output_dir, exist_ok=True)

    # Dateiname und Pfad zusammensetzen
    output_filename = f"{timestamp_prefix}_{clean_filename}.json"
    output_path = os.path.join(output_dir, output_filename)

    # Marker-Daten bereinigen und NumPy-Typen konvertieren
    markers: List[Dict[str, Any]] = []
    for cell in cell_list:
        cid = cell.get("cell_id", "")
        if isinstance(cid, (np.integer, int)):
            cid_val: Any = int(cid)
        else:
            cid_val = str(cid) if cid is not None else ""

        def _to_float(val: Any, default: float = 0.0) -> float:
            if val is None:
                return default
            try:
                return float(val)
            except (TypeError, ValueError):
                return default

        x_val = _to_float(cell.get("x_px", 0.0))
        y_val = _to_float(cell.get("y_px", 0.0))
        area_val = _to_float(cell.get("area_px", 0.0))
        conf_val = _to_float(cell.get("confidence", 0.0))
        status_val = str(cell.get("status", "UNKNOWN"))

        markers.append(
            {
                "cell_id": cid_val,
                "x_px": x_val,
                "y_px": y_val,
                "area_px": area_val,
                "confidence": conf_val,
                "status": status_val,
            }
        )

    payload: Dict[str, Any] = {
        "original_count": orig_cnt,
        "corrected_count": corr_cnt,
        "delta": delta,
        "image_path": str(image_path),
        "timestamp": timestamp_iso,
        "markers": markers,
    }

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(
                payload,
                f,
                indent=2,
                ensure_ascii=False,
                cls=_NumpySafeJSONEncoder,
            )
    except OSError as err:
        logger.error(
            "Fehler beim Speichern der Korrekturdatei %s: %s", output_path, err
        )
        raise

    logger.info(
        "Manuelle Korrektur gespeichert: %s (Original: %d, Korrigiert: %d, Delta: %+d)",
        output_path,
        orig_cnt,
        corr_cnt,
        delta,
    )

    return output_path

