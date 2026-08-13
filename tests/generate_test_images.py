"""Synthetischer Testbild-Generator für CellCounter Pro.

Erstellt realistische Mikroskopie-Testbilder mit Vignettierung, Helligkeitsgradienten,
Staubpartikeln, dichten Zell-Clustern und 16-Bit TIFFs für automatisierte Unit-Tests.
"""

import os
from typing import List, Tuple
import cv2
import numpy as np
import tifffile


def generate_vignetting_mask(shape: Tuple[int, int], strength: float = 0.5) -> np.ndarray:
    """Erzeugt eine radiale Vignettierungsmaske (dunkle Bildecken)."""
    h, w = shape
    cx, cy = w / 2.0, h / 2.0
    max_radius = np.sqrt(cx**2 + cy**2)

    y, x = np.ogrid[:h, :w]
    dist = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
    vignette = 1.0 - strength * (dist / max_radius) ** 2
    return np.clip(vignette, 0.2, 1.0)


def generate_linear_gradient(shape: Tuple[int, int], start_val: float = 1.2, end_val: float = 0.6) -> np.ndarray:
    """Erzeugt einen horizontalen Helligkeitsgradienten (heller links, dunkler rechts)."""
    h, w = shape
    gradient = np.linspace(start_val, end_val, w)
    return np.tile(gradient, (h, 1))


def draw_synthetic_cell(
    img: np.ndarray,
    cx: int,
    cy: int,
    radius: int,
    is_dead: bool = False,
    is_16bit: bool = False,
) -> None:
    """Zeichnet eine synthetische Zelle mit hellflächigem Körper und dunklem Rand/Kern."""
    scale = 65535 if is_16bit else 255
    bg_val = int(0.85 * scale)
    border_val = int(0.20 * scale)
    live_core_val = int(0.92 * scale)
    dead_core_val = int(0.15 * scale)

    # Äußerer dunkler Zellrand
    cv2.circle(img, (cx, cy), radius, border_val, -1)

    # Zellkörper
    body_radius = max(1, radius - 2)
    core_val = dead_core_val if is_dead else live_core_val
    cv2.circle(img, (cx, cy), body_radius, core_val, -1)


def add_dust_and_noise(img: np.ndarray, num_dust_particles: int = 30) -> np.ndarray:
    """Fügt kleine, unregelmäßige Staubpartikel und Rauschen hinzu."""
    h, w = img.shape[:2]
    result = img.copy()

    # Gaußsches Rauschen
    noise = np.random.normal(0, 5, (h, w)).astype(np.int16)
    result = np.clip(result.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    # Staubpartikel (dunkle kleine Flecken)
    for _ in range(num_dust_particles):
        dx = np.random.randint(10, w - 10)
        dy = np.random.randint(10, h - 10)
        dr = np.random.randint(1, 4)
        cv2.circle(result, (dx, dy), dr, np.random.randint(10, 50), -1)

    return result


def create_all_test_images(output_dir: str = "tests/data") -> List[str]:
    """Generiert alle Testbilder im Zielverzeichnis.

    Returns:
        List[str]: Pfade zu allen erzeugten Testdateien.
    """
    os.makedirs(output_dir, exist_ok=True)
    generated_files = []

    h, w = 600, 800

    # 1. Sauberes Testbild mit isolierten und verclusterten Zellen
    img1 = np.full((h, w), 215, dtype=np.uint8)
    # Einzelzellen
    cells_locs = [
        (100, 100, 15, False),
        (200, 100, 18, True),
        (300, 150, 16, False),
        (450, 120, 20, False),
        (600, 130, 14, True),
        # Verclusterte Zellgruppen (berührend)
        (200, 300, 16, False),
        (225, 305, 17, False),
        (212, 330, 15, True),
        # Dichter Cluster
        (450, 400, 18, False),
        (475, 405, 16, False),
        (460, 430, 17, True),
        (490, 425, 15, False),
        (435, 420, 16, False),
    ]

    for cx, cy, r, is_dead in cells_locs:
        draw_synthetic_cell(img1, cx, cy, r, is_dead)

    p1 = os.path.join(output_dir, "synthetic_clean_cluster.png")
    cv2.imwrite(p1, img1)
    generated_files.append(p1)

    # 2. Testbild mit Vignettierung & Helligkeitsgradient
    img2 = np.full((h, w), 215, dtype=np.float32)
    vignette = generate_vignetting_mask((h, w), strength=0.6)
    gradient = generate_linear_gradient((h, w), start_val=1.1, end_val=0.55)

    base_bg = img2 * vignette * gradient
    img2_uint8 = np.clip(base_bg, 0, 255).astype(np.uint8)

    for cx, cy, r, is_dead in cells_locs:
        draw_synthetic_cell(img2_uint8, cx, cy, r, is_dead)

    p2 = os.path.join(output_dir, "synthetic_vignetting_gradient.png")
    cv2.imwrite(p2, img2_uint8)
    generated_files.append(p2)

    # 3. Testbild mit Staubpartikeln & Rauschen
    img3 = img1.copy()
    img3 = add_dust_and_noise(img3, num_dust_particles=40)
    p3 = os.path.join(output_dir, "synthetic_dust_artifacts.png")
    cv2.imwrite(p3, img3)
    generated_files.append(p3)

    # 4. 16-Bit TIFF Mikroskopiebild
    img4_16 = np.full((h, w), 55000, dtype=np.uint16)
    for cx, cy, r, is_dead in cells_locs:
        draw_synthetic_cell(img4_16, cx, cy, r, is_dead, is_16bit=True)

    p4 = os.path.join(output_dir, "synthetic_16bit_microscopy.tiff")
    tifffile.imwrite(p4, img4_16)
    generated_files.append(p4)

    return generated_files


if __name__ == "__main__":
    files = create_all_test_images()
    print(f"{len(files)} Synthetische Testbilder erfolgreich erstellt:")
    for f in files:
        print(f" - {f}")
