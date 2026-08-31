import sys
import os
sys.path.insert(0, os.path.abspath("."))

import cv2
import tifffile
import numpy as np
from src.core.preprocessing import apply_clahe, denoise_image, to_grayscale
from src.core.segmentation import segment_cells
from src.core.viability import classify_viability
from src.core.tiff_handler import load_image_with_metadata
from src.utils.config_manager import load_config, get_preset

config = load_config('config.yaml')

images = [
    ('tests/data/synthetic_clean_cluster.png', 'Clean Cluster'),
    ('tests/data/synthetic_vignetting_gradient.png', 'Vignetting Gradient'),
    ('tests/data/synthetic_dust_artifacts.png', 'Dust Artifacts'),
    ('tests/data/synthetic_16bit_microscopy.tiff', '16-bit TIFF'),
]

for img_path, name in images:
    print(f"\n==========================================")
    print(f"Image: {name} ({img_path})")
    print(f"==========================================")
    if img_path.endswith('.tiff'):
        img, meta = load_image_with_metadata(img_path, 'test.tiff')
    else:
        img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
    
    # Analyze raw image stats
    print(f"Stats: shape={img.shape}, dtype={img.dtype}, min={img.min()}, max={img.max()}, mean={img.mean():.2f}, std={img.std():.2f}")
    
    for preset_name in ['Standard_Brightfield', 'Trypan_Blue_Viability', 'High_Density_Yeast']:
        preset = get_preset(preset_name, config)
        clahe = apply_clahe(img, clip_limit=preset['preprocessing']['clahe_clip_limit'], tile_grid_size=tuple(preset['preprocessing']['clahe_tile_grid_size']))
        denoised = denoise_image(clahe, kernel_size=preset['preprocessing']['gaussian_blur_kernel'])
        cells, markers, binary = segment_cells(denoised, preset['segmentation'])
        cells, summary = classify_viability(denoised, cells, preset['viability'])
        
        print(f"\n  [Preset: {preset_name}]")
        print(f"  Total cells: {len(cells)} | Live: {summary.get('live_cells',0)} | Dead: {summary.get('dead_cells',0)} | Viability: {summary.get('viability_pct',0):.1f}%")
        
        # Detail cell metrics
        cell_info = []
        for c in cells:
            cell_info.append(f"    Cell #{c['cell_id']}: center=({c['x_px']:.1f}, {c['y_px']:.1f}), area={c['area_px']:.1f}, circ={c['circularity']:.3f}, solid={c['solidity']:.3f}, status={c.get('status','N/A')}, int_diff={c.get('intensity_diff', 0.0)}")
        print("\n".join(cell_info))
