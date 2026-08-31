import sys
import os
sys.path.insert(0, os.path.abspath("."))

import cv2
import numpy as np
from src.core.preprocessing import apply_clahe, denoise_image
from src.core.segmentation import segment_cells
from src.core.viability import classify_viability
from src.utils.config_manager import load_config, get_preset

def analyze_image_statistics(gray: np.ndarray):
    """Calculates image stats: histogram distribution, local contrast, brightness gradient."""
    # 1. Brightness & Histogram
    mean_val = float(np.mean(gray))
    std_val = float(np.std(gray))
    p10, p50, p90 = np.percentile(gray, [10, 50, 90])
    
    # 2. Local Contrast (Standard deviation of local patches or Laplacian variance)
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    local_contrast = float(laplacian.var())
    
    # 3. Brightness Gradient (Sobel or corner-to-corner difference)
    sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=5)
    sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=5)
    gradient_mag = float(np.mean(np.sqrt(sobelx**2 + sobely**2)))
    
    # Vignetting indicator: center vs corners
    h, w = gray.shape
    center_patch = gray[h//4:3*h//4, w//4:3*w//4]
    corners = np.concatenate([
        gray[:h//4, :w//4].ravel(),
        gray[:h//4, 3*w//4:].ravel(),
        gray[3*h//4:, :w//4].ravel(),
        gray[3*h//4:, 3*w//4:].ravel()
    ])
    vignette_ratio = float(np.mean(center_patch) / (np.mean(corners) + 1e-5))
    
    return {
        "mean": mean_val,
        "std": std_val,
        "p10": p10,
        "p50": p50,
        "p90": p90,
        "laplacian_var": local_contrast,
        "gradient_mag": gradient_mag,
        "vignette_ratio": vignette_ratio,
    }

def compute_cell_confidence(cell: dict, gray_work: np.ndarray) -> float:
    """Computes confidence score in [0.0, 1.0] based on circularity, solidity, and local CNR."""
    circ = cell.get("circularity", 0.5)
    solid = cell.get("solidity", 0.5)
    
    # Contrast-to-Noise Ratio (CNR) in local cell region vs background
    mask = cell["mask_work"]
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    dilated = cv2.dilate(mask, kernel)
    ring = cv2.subtract(dilated, mask)
    
    cell_pixels = gray_work[mask == 255]
    bg_pixels = gray_work[ring == 255]
    
    if len(cell_pixels) > 0 and len(bg_pixels) > 0:
        signal = abs(float(np.mean(cell_pixels)) - float(np.mean(bg_pixels)))
        noise = float(np.std(bg_pixels)) + 1e-5
        cnr = signal / noise
        # Normalize CNR: 0 to 10+ maps to [0, 1]
        cnr_score = min(1.0, cnr / 5.0)
    else:
        cnr_score = 0.5
        
    # Weighted combination
    score = 0.35 * circ + 0.35 * solid + 0.30 * cnr_score
    return round(float(np.clip(score, 0.0, 1.0)), 3)

images = [
    ('tests/data/synthetic_clean_cluster.png', 'Clean Cluster'),
    ('tests/data/synthetic_vignetting_gradient.png', 'Vignetting Gradient'),
    ('tests/data/synthetic_dust_artifacts.png', 'Dust Artifacts'),
]

config = load_config('config.yaml')
preset = get_preset('Standard_Brightfield', config)

for path, name in images:
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    stats = analyze_image_statistics(img)
    print(f"\nStats for {name}:")
    for k, v in stats.items():
        print(f"  {k}: {v:.2f}")
    
    clahe = apply_clahe(img)
    denoised = denoise_image(clahe)
    cells, markers, binary = segment_cells(denoised, preset['segmentation'])
    
    print(f"  Segmented Cells & Confidence Scores:")
    for c in cells:
        conf = compute_cell_confidence(c, denoised)
        tag = "GREEN (>=0.7)" if conf >= 0.7 else ("YELLOW (0.4-0.7)" if conf >= 0.4 else "RED (<0.4)")
        print(f"    Cell #{c['cell_id']} at ({c['x_px']:.1f},{c['y_px']:.1f}): circ={c['circularity']:.3f}, solid={c['solidity']:.3f} -> Conf={conf:.3f} [{tag}]")
