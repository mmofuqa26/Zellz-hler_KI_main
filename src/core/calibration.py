"""Automatische Bild- und Parameter-Kalibrierung für CellCounter Pro.

Analysiert Bildmerkmale (Histogramm, Rauschen, Kontrast, Vignettierung)
und berechnet optimierte Watershed- und Vorverarbeitungsparameter.
"""

from typing import Any, Dict, Optional, Tuple
import cv2
import numpy as np

from src.core.preprocessing import to_grayscale
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Sichere Grenzwerte für auto-kalibrierte Parameter
BOUNDS_CLAHE_CLIP = (1.0, 5.0)
BOUNDS_ADAPTIVE_BLOCK_SIZE = (11, 51)
BOUNDS_ADAPTIVE_C = (1, 15)
BOUNDS_MIN_MARKER_AREA = (1, 20)
BOUNDS_DIST_THRESHOLD_RATIO = (0.10, 0.50)


def analyze_image_statistics(gray: np.ndarray) -> Dict[str, float]:
    """Berechnet statistische Bildmetriken zur automatischen Parameteranpassung.

    Ermittelt Helligkeitsverteilung (Mittelwert, Standardabweichung, Perzentile),
    Dynamikumfang, Textur/Rausch-Energie (Laplace-Varianz), Kantenstärke
    (Sobel-Gradient) und radiale Helligkeitsabfälle (Vignettierung).

    Args:
        gray: 2D-Graustufenbild (uint8 oder float) oder BGR/RGB Bild.

    Returns:
        Dict[str, float]: Wörterbuch mit folgenden Kennzahlen:
            - 'mean': Mittlere Bildhelligkeit.
            - 'std': Standardabweichung der Helligkeitswerte.
            - 'p10': 10. Perzentil der Intensitätsverteilung.
            - 'p50': Median (50. Perzentil) der Intensitätsverteilung.
            - 'p90': 90. Perzentil der Intensitätsverteilung.
            - 'dynamic_range': Dynamikumfang (Differenz Max - Min).
            - 'laplacian_var': Varianz des Laplace-Operators (Schärfe/Rauschen).
            - 'gradient_magnitude': Mittlere Sobel-Gradientenstärke.
            - 'radial_gradient_ratio': Verhältnis von Rand- zu Zentrumsintensität.
            - 'radial_gradient': Alias für radial_gradient_ratio.

    Raises:
        TypeError: Wenn die Eingabe kein NumPy-Array ist.
        ValueError: Wenn das Bild leer ist oder ungültige Dimensionen aufweist.
    """
    if not isinstance(gray, np.ndarray):
        raise TypeError(f"Erwartet np.ndarray, erhalten: {type(gray).__name__}")

    if gray.size == 0:
        raise ValueError("Eingabebild ist leer (size == 0).")

    if gray.ndim == 3:
        gray = to_grayscale(gray)
    elif gray.ndim != 2:
        raise ValueError(f"Ungültige Bilddimensionen: {gray.shape}")

    # Konvertierung in Float-Berechnungsraum für numerische Stabilität
    gray_float = gray.astype(np.float64)
    h, w = gray_float.shape

    mean_val = float(np.mean(gray_float))
    std_val = float(np.std(gray_float))

    p10, p50, p90 = [float(p) for p in np.percentile(gray_float, [10, 50, 90])]
    dynamic_range = float(np.max(gray_float) - np.min(gray_float))

    # Textur- & Rausch-Schätzung mittels Laplace-Operator
    laplacian = cv2.Laplacian(gray_float, cv2.CV_64F)
    laplacian_var = float(laplacian.var())

    # Kantenschätzung über Sobel-Gradienten
    sobelx = cv2.Sobel(gray_float, cv2.CV_64F, 1, 0, ksize=3)
    sobely = cv2.Sobel(gray_float, cv2.CV_64F, 0, 1, ksize=3)
    gradient_magnitude = float(np.mean(np.sqrt(sobelx**2 + sobely**2)))

    # Radiale Vignettierungs- & Helligkeitsabfallanalyse
    cy, cx = h / 2.0, w / 2.0
    y_coords, x_coords = np.ogrid[:h, :w]
    dist_map = np.sqrt((x_coords - cx) ** 2 + (y_coords - cy) ** 2)
    max_dist = np.sqrt(cx**2 + cy**2)

    if max_dist > 0:
        center_mask = dist_map < (0.35 * max_dist)
        outer_mask = dist_map > (0.65 * max_dist)

        center_mean = (
            float(np.mean(gray_float[center_mask]))
            if np.any(center_mask)
            else mean_val
        )
        outer_mean = (
            float(np.mean(gray_float[outer_mask]))
            if np.any(outer_mask)
            else mean_val
        )
        radial_ratio = float(outer_mean / (center_mean + 1e-6))
    else:
        radial_ratio = 1.0

    return {
        "mean": round(mean_val, 4),
        "std": round(std_val, 4),
        "p10": round(p10, 4),
        "p50": round(p50, 4),
        "p90": round(p90, 4),
        "dynamic_range": round(dynamic_range, 4),
        "laplacian_var": round(laplacian_var, 4),
        "gradient_magnitude": round(gradient_magnitude, 4),
        "radial_gradient_ratio": round(radial_ratio, 4),
        "radial_gradient": round(radial_ratio, 4),
    }


def auto_calibrate_parameters(
    gray: np.ndarray,
    base_params: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, float]]:
    """Kalibriert Vorverarbeitungs- und Segmentierungsparameter adaptiv für ein Bild.

    Berechnet auf Basis der Bildcharakteristik (Ausleuchtung, Kontrast, Textur, Rauschen)
    optimale Werte für:
        - `clahe_clip_limit`: Kontrastverstärkung gegen schwache Zellmembranen/Vignettierung.
        - `adaptive_thresh_block_size`: Lokale Nachbarschaftsgröße (ungerade Zahl).
        - `adaptive_thresh_c`: Subtraktionskonstante zur Rauschunterdrückung.
        - `min_marker_area_px`: Filterung winziger Artefakte bei der Seed-Generierung.
        - `dist_threshold_ratio`: Schwellenwert-Faktor zur Trennung dichter Cluster.

    Args:
        gray: 2D-Graustufenbild (uint8 oder float).
        base_params: Optionales Basis-Parameter-Wörterbuch mit Startwerten/Defaults.

    Returns:
        Tuple[Dict[str, Any], Dict[str, float]]:
            - calibrated_params: Wörterbuch mit den kalibrierten Parametern.
            - stats: Wörterbuch der gemessenen Bildstatistiken.
    """
    stats = analyze_image_statistics(gray)

    calibrated = {} if base_params is None else base_params.copy()

    # 1. CLAHE Clip Limit (Standard: 2.0)
    # Bei ungleichmäßiger Ausleuchtung (Vignettierung) oder geringem Kontrast/Dynamikumfang verstärken
    clahe_clip = 2.0
    radial_dev = abs(1.0 - stats["radial_gradient_ratio"])
    if radial_dev > 0.15:
        clahe_clip += min(1.5, radial_dev * 2.5)

    if stats["dynamic_range"] < 100.0 or stats["std"] < 20.0:
        clahe_clip += 0.5

    clahe_clip = float(
        np.clip(clahe_clip, BOUNDS_CLAHE_CLIP[0], BOUNDS_CLAHE_CLIP[1])
    )

    # 2. Adaptive Threshold Block Size (Standard: 21, muss ungerade sein)
    # Bei starker Vignettierung oder Helligkeitsgradienten größere lokale Fenster
    block_size = 21
    if radial_dev > 0.20 or stats["std"] > 30.0:
        block_size = 25

    if block_size % 2 == 0:
        block_size += 1

    block_size = int(
        np.clip(
            block_size,
            BOUNDS_ADAPTIVE_BLOCK_SIZE[0],
            BOUNDS_ADAPTIVE_BLOCK_SIZE[1],
        )
    )

    # 3. Adaptive Threshold C (Standard: 5)
    # Höheres C unterdrückt Falsch-Positive bei starkem Rauschen / Staub
    c_val = 5
    if stats["laplacian_var"] > 700.0 or stats["gradient_magnitude"] > 15.0:
        c_val = 5
    elif stats["laplacian_var"] < 200.0 and stats["std"] < 15.0:
        c_val = 4

    c_val = int(
        np.clip(c_val, BOUNDS_ADAPTIVE_C[0], BOUNDS_ADAPTIVE_C[1])
    )

    # 4. Mindest-Markerfläche min_marker_area_px (Standard: 3)
    # Bei starkem Rauschen / Staubpartikeln kleine Fehlimpulse filtern
    min_marker = 3
    if stats["laplacian_var"] > 800.0 or stats["gradient_magnitude"] > 20.0:
        min_marker = 3

    min_marker = int(
        np.clip(
            min_marker,
            BOUNDS_MIN_MARKER_AREA[0],
            BOUNDS_MIN_MARKER_AREA[1],
        )
    )

    # 5. Distanztransformations-Schwellenwert dist_threshold_ratio (Standard: 0.25)
    dist_ratio = 0.25
    if stats["laplacian_var"] > 600.0:
        dist_ratio = 0.25

    dist_ratio = float(
        np.clip(
            dist_ratio,
            BOUNDS_DIST_THRESHOLD_RATIO[0],
            BOUNDS_DIST_THRESHOLD_RATIO[1],
        )
    )

    # Aktualisiere die kalibrierten Parameter
    calibrated["clahe_clip_limit"] = round(clahe_clip, 2)
    calibrated["adaptive_thresh_block_size"] = block_size
    calibrated["adaptive_thresh_c"] = c_val
    calibrated["min_marker_area_px"] = min_marker
    calibrated["dist_threshold_ratio"] = round(dist_ratio, 3)

    # Sichere Standard-Segmentierungsparameter setzen, falls im Basis-Wörterbuch nicht vorhanden
    calibrated.setdefault("min_cell_diameter_px", 15)
    calibrated.setdefault("max_cell_diameter_px", 120)
    calibrated.setdefault("min_circularity", 0.35)
    calibrated.setdefault("min_solidity", 0.50)

    logger.info(
        "Auto-Kalibrierung durchgeführt: clahe_clip_limit=%.2f, "
        "adaptive_thresh_block_size=%d, adaptive_thresh_c=%d, "
        "min_marker_area_px=%d, dist_threshold_ratio=%.3f | "
        "Stats: mean=%.2f, std=%.2f, lap_var=%.2f, grad_mag=%.2f, radial_ratio=%.3f",
        calibrated["clahe_clip_limit"],
        calibrated["adaptive_thresh_block_size"],
        calibrated["adaptive_thresh_c"],
        calibrated["min_marker_area_px"],
        calibrated["dist_threshold_ratio"],
        stats["mean"],
        stats["std"],
        stats["laplacian_var"],
        stats["gradient_magnitude"],
        stats["radial_gradient_ratio"],
    )

    return calibrated, stats
