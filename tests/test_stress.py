"""Adversarial, Empirical Stress, and Fuzzing Tests for CellCounter Pro.

Targeting:
- Extreme image inputs (pure black, pure white, noise, vignette, odd dimensions, float arrays)
- Auto-calibration numerical stability (div-by-zero, bounds clamping, NaN/Inf robustness)
- Pipeline end-to-end resilience under adversarial conditions
- Confidence scoring edge cases (zero perimeter, single-pixel, concave/degenerate contours, out-of-bounds)
- Manual correction persistence (large counts, negative deltas, empty markers, special filenames, nested paths)
- Overlay rendering and metrics edge cases
- Monte Carlo randomized fuzzing
"""

import json
import math
import os
import shutil
import tempfile
import numpy as np
import pytest
import cv2

from src.core.calibration import (
    analyze_image_statistics,
    auto_calibrate_parameters,
    BOUNDS_CLAHE_CLIP,
    BOUNDS_ADAPTIVE_BLOCK_SIZE,
    BOUNDS_ADAPTIVE_C,
    BOUNDS_MIN_MARKER_AREA,
    BOUNDS_DIST_THRESHOLD_RATIO,
)
from src.core.confidence import (
    compute_cell_confidence,
    get_confidence_category,
    THRESHOLD_HIGH_CONFIDENCE,
    THRESHOLD_LOW_CONFIDENCE,
)
from src.core.metrics import compute_summary_statistics
from src.core.preprocessing import (
    to_grayscale,
    downscale_image_if_needed,
    apply_clahe,
    denoise_image,
)
from src.core.segmentation import segment_cells, find_local_peaks, fill_binary_holes
from src.core.viability import classify_viability
from src.utils.io_export import (
    create_annotated_overlay,
    generate_csv_data,
    save_manual_correction,
)


# =============================================================================
# 1. EXTREME IMAGE INPUTS & AUTO-CALIBRATION NUMERICAL STABILITY
# =============================================================================


class TestCalibrationStressAndAdversarial:
    """Stress tests for auto-calibration and statistical analysis."""

    @pytest.mark.parametrize(
        "shape,fill_val,dtype",
        [
            ((100, 100), 0, np.uint8),            # Pure black uint8
            ((100, 100), 255, np.uint8),          # Pure white uint8
            ((100, 100), 128, np.uint8),          # Uniform gray uint8
            ((50, 50), 0.0, np.float32),          # Pure black float32
            ((50, 50), 1.0, np.float32),          # Pure white float32 (normalized)
            ((50, 50), 255.0, np.float64),        # Pure white float64
            ((5, 5), 0, np.uint8),                # Tiny 5x5
            ((1, 1), 100, np.uint8),              # 1x1 single pixel
            ((2, 500), 200, np.uint8),            # Extreme aspect ratio (wide)
            ((500, 2), 50, np.uint8),             # Extreme aspect ratio (tall)
            ((33, 47), 77, np.uint8),             # Prime dimensions
        ],
    )
    def test_analyze_statistics_uniform_and_extreme_shapes(self, shape, fill_val, dtype):
        """Verify analyze_image_statistics handles uniform and extreme shaped images without crashing."""
        img = np.full(shape, fill_val, dtype=dtype)
        stats = analyze_image_statistics(img)

        assert isinstance(stats, dict)
        required_keys = [
            "mean", "std", "p10", "p50", "p90", "dynamic_range",
            "laplacian_var", "gradient_magnitude", "radial_gradient_ratio",
        ]
        for key in required_keys:
            assert key in stats
            assert not math.isnan(stats[key]), f"Stat {key} is NaN for shape {shape}"
            assert not math.isinf(stats[key]), f"Stat {key} is Inf for shape {shape}"

        # On uniform images, dynamic range and std must be 0
        assert stats["std"] == 0.0
        assert stats["dynamic_range"] == 0.0
        assert stats["laplacian_var"] == 0.0
        assert stats["gradient_magnitude"] == 0.0

    def test_analyze_statistics_high_frequency_noise(self):
        """Stress test with high-frequency Gaussian and salt-and-pepper noise."""
        np.random.seed(42)
        noise_uniform = np.random.randint(0, 256, (256, 256), dtype=np.uint8)
        stats_noise = analyze_image_statistics(noise_uniform)
        assert stats_noise["laplacian_var"] > 500.0
        assert stats_noise["gradient_magnitude"] > 20.0

        # Gaussian noise
        gaussian_noise = np.clip(np.random.normal(128, 50, (256, 256)), 0, 255).astype(np.uint8)
        stats_gauss = analyze_image_statistics(gaussian_noise)
        assert stats_gauss["std"] > 30.0

    def test_analyze_statistics_extreme_vignette_and_inverted_vignette(self):
        """Stress test with extreme center-to-edge falloff and edge-to-center falloff."""
        h, w = 200, 200
        y, x = np.ogrid[:h, :w]
        cy, cx = h / 2.0, w / 2.0
        dist = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
        max_dist = np.sqrt(cx ** 2 + cy ** 2)

        # Standard vignette: bright center, black borders
        vignette = np.clip(255 * (1.0 - (dist / max_dist) ** 2), 0, 255).astype(np.uint8)
        stats_vig = analyze_image_statistics(vignette)
        assert stats_vig["radial_gradient_ratio"] < 0.60

        # Inverted vignette: black center, bright borders
        inv_vignette = np.clip(255 * (dist / max_dist), 0, 255).astype(np.uint8)
        stats_inv = analyze_image_statistics(inv_vignette)
        assert stats_inv["radial_gradient_ratio"] > 1.40

    @pytest.mark.parametrize(
        "image_scenario",
        [
            np.zeros((100, 100), dtype=np.uint8),                           # Pure black
            np.full((100, 100), 255, dtype=np.uint8),                       # Pure white
            np.random.randint(0, 256, (128, 128), dtype=np.uint8),          # Pure noise
            np.tile(np.array([[0, 255], [255, 0]], dtype=np.uint8), (50, 50)), # Checkerboard
            np.linspace(0, 255, 10000, dtype=np.uint8).reshape(100, 100),   # Linear gradient
        ],
    )
    def test_auto_calibration_bounds_clamping_strictness(self, image_scenario):
        """Ensure that calibrated parameters strictly satisfy bounds under all extreme inputs."""
        calibrated, stats = auto_calibrate_parameters(image_scenario)

        # 1. CLAHE Clip Limit
        assert BOUNDS_CLAHE_CLIP[0] <= calibrated["clahe_clip_limit"] <= BOUNDS_CLAHE_CLIP[1]
        # 2. Adaptive Block Size
        assert BOUNDS_ADAPTIVE_BLOCK_SIZE[0] <= calibrated["adaptive_thresh_block_size"] <= BOUNDS_ADAPTIVE_BLOCK_SIZE[1]
        assert calibrated["adaptive_thresh_block_size"] % 2 == 1, "Block size must be odd"
        # 3. Adaptive C
        assert BOUNDS_ADAPTIVE_C[0] <= calibrated["adaptive_thresh_c"] <= BOUNDS_ADAPTIVE_C[1]
        # 4. Min Marker Area
        assert BOUNDS_MIN_MARKER_AREA[0] <= calibrated["min_marker_area_px"] <= BOUNDS_MIN_MARKER_AREA[1]
        # 5. Dist Threshold Ratio
        assert BOUNDS_DIST_THRESHOLD_RATIO[0] <= calibrated["dist_threshold_ratio"] <= BOUNDS_DIST_THRESHOLD_RATIO[1]

    def test_auto_calibration_preserves_custom_base_params(self):
        """Ensure base_params keys are preserved and updated properly."""
        custom_base = {
            "custom_metadata_key": "lab_experiment_42",
            "min_cell_diameter_px": 25,
            "max_cell_diameter_px": 80,
            "clahe_clip_limit": 1.0,
        }
        calibrated, _ = auto_calibrate_parameters(np.full((100, 100), 128, dtype=np.uint8), base_params=custom_base)
        assert calibrated["custom_metadata_key"] == "lab_experiment_42"
        assert calibrated["min_cell_diameter_px"] == 25
        assert calibrated["max_cell_diameter_px"] == 80


# =============================================================================
# 2. CONFIDENCE SCORING ADVERSARIAL & EDGE CASES
# =============================================================================


class TestConfidenceAdversarialAndEdgeCases:
    """Stress tests for cell confidence calculation and edge cases."""

    def test_confidence_zero_perimeter_and_single_point(self):
        """Single point or 0-perimeter contours should receive 0 circularity and no div-by-zero."""
        gray = np.full((100, 100), 128, dtype=np.uint8)

        # Single point contour: (1, 1, 2)
        cnt_single = np.array([[[50, 50]]], dtype=np.int32)
        cell = {"cell_id": 1, "contour_work": cnt_single, "x_px": 50, "y_px": 50}

        enriched = compute_cell_confidence(cell, gray)
        assert 0.0 <= enriched["confidence"] <= 1.0
        assert enriched["confidence_category"] == "RED"

    def test_confidence_two_point_line_contour(self):
        """Line contour (area=0, perimeter>0) should have circularity=0 and solidity=0."""
        gray = np.full((100, 100), 128, dtype=np.uint8)
        cnt_line = np.array([[[10, 10]], [[10, 30]]], dtype=np.int32)
        cell = {"cell_id": 2, "contour_work": cnt_line, "x_px": 10, "y_px": 20}

        enriched = compute_cell_confidence(cell, gray)
        assert enriched["confidence"] < 0.40
        assert enriched["confidence_category"] == "RED"

    def test_confidence_concave_star_and_fractal_shapes(self):
        """Star-shaped or highly concave contours should suffer circularity and solidity penalties."""
        gray = np.full((200, 200), 200, dtype=np.uint8)
        # Create a 5-pointed star contour
        pts = []
        cx, cy = 100, 100
        for i in range(10):
            r = 40 if i % 2 == 0 else 10
            angle = i * math.pi / 5.0
            pts.append([[int(cx + r * math.cos(angle)), int(cy + r * math.sin(angle))]])
        star_cnt = np.array(pts, dtype=np.int32)

        # Draw dark star on white background
        cv2.drawContours(gray, [star_cnt], -1, 50, -1)

        cell = {"cell_id": 3, "contour_work": star_cnt, "x_px": 100, "y_px": 100}
        enriched = compute_cell_confidence(cell, gray)

        # A star should have significantly lower confidence than a circle
        assert enriched["confidence"] < 0.70
        assert enriched["confidence_category"] in ["YELLOW", "RED"]

    def test_confidence_cell_at_image_boundary(self):
        """Cell contour located at the exact border/corner of the image."""
        gray = np.full((100, 100), 180, dtype=np.uint8)
        # Cell hugging corner (0, 0)
        cnt_corner = np.array([[[0, 0]], [[15, 0]], [[15, 15]], [[0, 15]]], dtype=np.int32)
        cell = {"cell_id": 4, "contour_work": cnt_corner, "x_px": 7, "y_px": 7}

        enriched = compute_cell_confidence(cell, gray)
        assert 0.0 <= enriched["confidence"] <= 1.0
        assert enriched["confidence_category"] in ["GREEN", "YELLOW", "RED"]

    def test_confidence_cell_larger_than_image_or_empty_background(self):
        """Mask fills entire image so ring_pixels has 0 size."""
        gray = np.full((50, 50), 100, dtype=np.uint8)
        cnt_full = np.array([[[0, 0]], [[49, 0]], [[49, 49]], [[0, 49]]], dtype=np.int32)
        cell = {"cell_id": 5, "contour_work": cnt_full, "x_px": 25, "y_px": 25}

        enriched = compute_cell_confidence(cell, gray)
        assert 0.0 <= enriched["confidence"] <= 1.0
        assert enriched["cnr"] == 0.0

    def test_confidence_empty_cell_dict_fallbacks(self):
        """Completely empty cell dictionary with no contours, coordinates, or metrics."""
        gray = np.full((100, 100), 128, dtype=np.uint8)
        cell = {}
        enriched = compute_cell_confidence(cell, gray)
        assert "confidence" in enriched
        assert "confidence_category" in enriched
        assert "cnr" in enriched
        assert 0.0 <= enriched["confidence"] <= 1.0

    @pytest.mark.parametrize(
        "score,expected_cat",
        [
            (0.0, "RED"),
            (0.3999, "RED"),
            (0.40, "YELLOW"),
            (0.6999, "YELLOW"),
            (0.70, "GREEN"),
            (1.0, "GREEN"),
            (1.5, "GREEN"),
            (-0.5, "RED"),
        ],
    )
    def test_get_confidence_category_boundary_values(self, score, expected_cat):
        """Verify strict classification across all boundary points."""
        assert get_confidence_category(score) == expected_cat

    def test_confidence_invalid_weights_and_inputs(self):
        """Check exception raising for invalid arguments."""
        gray = np.full((50, 50), 128, dtype=np.uint8)
        with pytest.raises(TypeError):
            compute_cell_confidence("not-a-dict", gray)

        with pytest.raises(TypeError):
            compute_cell_confidence({}, "not-an-array")

        with pytest.raises(ValueError):
            compute_cell_confidence({}, np.array([]))

        with pytest.raises(ValueError):
            compute_cell_confidence({}, gray, weights=(0.5, 0.5))  # Only 2 weights


# =============================================================================
# 3. END-TO-END PIPELINE RESILIENCE UNDER EXTREME INPUTS
# =============================================================================


class TestPipelineExtremeInputs:
    """Run full end-to-end analysis on extreme images without any unhandled exceptions."""

    def _run_full_pipeline(self, img_input):
        gray = to_grayscale(img_input)
        gray_work, scale = downscale_image_if_needed(gray, max_dimension=1024)
        calibrated, stats = auto_calibrate_parameters(gray_work)
        clahe = apply_clahe(gray_work, clip_limit=calibrated["clahe_clip_limit"])
        denoised = denoise_image(clahe)
        cell_list, markers, binary = segment_cells(denoised, calibrated, scale_factor=scale)
        cell_list, viab_summary = classify_viability(denoised, cell_list, {"enabled": True, "ring_width_px": 4})
        summary = compute_summary_statistics(cell_list, viab_summary)
        overlay = create_annotated_overlay(img_input, cell_list)
        csv_str = generate_csv_data(cell_list)
        return cell_list, summary, overlay, csv_str

    def test_pipeline_on_pure_black_image(self):
        """Pipeline must gracefully handle pure black (0 cells detected, no crashes)."""
        black_img = np.zeros((300, 300), dtype=np.uint8)
        cells, summary, overlay, csv_str = self._run_full_pipeline(black_img)
        assert len(cells) == 0
        assert summary["total_cells"] == 0
        assert summary["uncertain_cells"] == 0
        assert summary["problematic_cells"] == 0
        assert overlay.shape == (300, 300, 3)
        assert "Cell_ID;Status;Confidence" in csv_str

    def test_pipeline_on_pure_white_image(self):
        """Pipeline must gracefully handle pure white (0 cells detected, no crashes)."""
        white_img = np.full((300, 300), 255, dtype=np.uint8)
        cells, summary, overlay, csv_str = self._run_full_pipeline(white_img)
        assert len(cells) == 0
        assert summary["total_cells"] == 0
        assert overlay.shape == (300, 300, 3)

    def test_pipeline_on_high_frequency_random_noise(self):
        """Pipeline must survive pure high-frequency noise without crashing."""
        np.random.seed(123)
        noise_img = np.random.randint(0, 256, (300, 300), dtype=np.uint8)
        cells, summary, overlay, csv_str = self._run_full_pipeline(noise_img)
        # Any artifacts filtered or classified
        assert isinstance(summary["total_cells"], int)
        assert summary["uncertain_cells"] + summary["problematic_cells"] + summary["high_confidence_cells"] == len(cells)

    def test_pipeline_on_non_square_odd_dimensions(self):
        """Pipeline on odd dimensions (e.g. 173 x 289)."""
        odd_img = np.full((173, 289), 200, dtype=np.uint8)
        # Draw 2 synthetic cells
        cv2.circle(odd_img, (50, 50), 15, 50, -1)
        cv2.circle(odd_img, (150, 100), 18, 50, -1)
        cells, summary, overlay, csv_str = self._run_full_pipeline(odd_img)
        assert summary["total_cells"] >= 2


# =============================================================================
# 4. MANUAL CORRECTION PERSISTENCE ADVERSARIAL TESTS
# =============================================================================


class TestManualCorrectionPersistenceAdversarial:
    """Stress test manual correction persistence with edge-case payloads."""

    @pytest.fixture
    def temp_dir(self):
        d = tempfile.mkdtemp(prefix="corr_stress_")
        yield d
        shutil.rmtree(d, ignore_errors=True)

    def test_persistence_huge_counts_and_negative_delta(self, temp_dir):
        """Handle counts up to billions and negative delta."""
        out_path = save_manual_correction(
            filename="large_scale_sample.tif",
            original_count=1_000_000,
            corrected_count=500_000,
            cell_list=[],
            image_path="/data/microscopy/large_scale.tif",
            output_dir=temp_dir,
        )
        assert os.path.exists(out_path)
        with open(out_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["original_count"] == 1_000_000
        assert data["corrected_count"] == 500_000
        assert data["delta"] == -500_000
        assert data["markers"] == []

    def test_persistence_special_characters_in_filename(self, temp_dir):
        """Filenames with spaces, umlauts, dots, brackets, and path traversal characters."""
        special_names = [
            "Zellzählung #1 [40x] (DAPI+Trypan) - Test 100%.png",
            "../../etc/passwd_evil.png",
            "C:\\Windows\\System32\\sample.tif",
            "   trimmed_name   .jpg",
            "---....---.tif",
        ]
        for name in special_names:
            out_path = save_manual_correction(
                filename=name,
                original_count=10,
                corrected_count=12,
                cell_list=[],
                output_dir=temp_dir,
            )
            assert os.path.exists(out_path)
            # Ensure the file is saved strictly inside temp_dir
            assert os.path.commonpath([temp_dir, os.path.abspath(out_path)]) == os.path.abspath(temp_dir)

    def test_persistence_numpy_types_and_missing_marker_attributes(self, temp_dir):
        """Cell list with strange types, numpy types, and missing attributes."""
        cell_list = [
            {
                "cell_id": np.int64(99),
                "x_px": np.float32(123.456),
                "y_px": np.float64(789.012),
                "area_px": np.int32(450),
                "confidence": np.float32(0.875),
                "status": "LIVE",
            },
            {
                # Missing x_px, y_px, area_px, confidence
                "cell_id": "Cell_Alpha",
                "custom_prop": "ignored",
            },
            {
                # None values
                "cell_id": None,
                "x_px": None,
                "confidence": None,
            },
        ]

        out_path = save_manual_correction(
            filename="dirty_markers.png",
            original_count=3,
            corrected_count=5,
            cell_list=cell_list,
            output_dir=temp_dir,
        )
        assert os.path.exists(out_path)

        with open(out_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert len(data["markers"]) == 3
        # First marker
        assert data["markers"][0]["cell_id"] == 99
        assert pytest.approx(data["markers"][0]["x_px"], 0.001) == 123.456
        assert pytest.approx(data["markers"][0]["confidence"], 0.001) == 0.875
        # Second marker defaults
        assert data["markers"][1]["cell_id"] == "Cell_Alpha"
        assert data["markers"][1]["x_px"] == 0.0
        assert data["markers"][1]["confidence"] == 0.0
        # Third marker defaults
        assert data["markers"][2]["cell_id"] == ""
        assert data["markers"][2]["x_px"] == 0.0

    def test_persistence_auto_creates_deeply_nested_directory(self, temp_dir):
        """Nested directories like deep/sub/folder/data/corrections must be auto-created."""
        deep_dir = os.path.join(temp_dir, "nested", "sub", "directory", "corrections")
        out_path = save_manual_correction(
            filename="deep_test.png",
            original_count=5,
            corrected_count=5,
            cell_list=[],
            output_dir=deep_dir,
        )
        assert os.path.exists(out_path)
        assert os.path.isdir(deep_dir)


# =============================================================================
# 5. OVERLAY RENDERING & CSV EXPORT ADVERSARIAL TESTS
# =============================================================================


class TestOverlayAndExportAdversarial:
    """Stress tests for overlay annotation and CSV generation."""

    def test_overlay_extreme_coordinates_and_empty_list(self):
        """Overlay with coordinates far outside image boundaries or empty list."""
        img = np.full((100, 100, 3), 200, dtype=np.uint8)
        overlay_empty = create_annotated_overlay(img, [])
        assert overlay_empty.shape == (100, 100, 3)

        out_of_bounds_cells = [
            {"cell_id": 1, "x_px": -500.0, "y_px": -300.0, "confidence": 0.9, "confidence_category": "GREEN"},
            {"cell_id": 2, "x_px": 5000.0, "y_px": 9000.0, "confidence": 0.2, "confidence_category": "RED"},
            {"cell_id": 3, "x_px": 50.0, "y_px": 50.0, "confidence": 0.55, "confidence_category": "YELLOW"},
        ]
        overlay_oob = create_annotated_overlay(img, out_of_bounds_cells)
        assert overlay_oob.shape == (100, 100, 3)

    def test_overlay_grayscale_and_bgr_inputs(self):
        """create_annotated_overlay must support both 2D grayscale and 3D BGR images."""
        gray = np.full((80, 80), 128, dtype=np.uint8)
        bgr = np.full((80, 80, 3), 128, dtype=np.uint8)

        cells = [{"cell_id": 1, "x_px": 40, "y_px": 40, "confidence": 0.8, "confidence_category": "GREEN"}]
        res_gray = create_annotated_overlay(gray, cells)
        res_bgr = create_annotated_overlay(bgr, cells)

        assert res_gray.shape == (80, 80, 3)
        assert res_bgr.shape == (80, 80, 3)

    def test_csv_export_special_strings_and_empty_list(self):
        """CSV export handles empty list and strange characters in status/cell_id."""
        csv_empty = generate_csv_data([])
        assert "Cell_ID;Status;Confidence;Confidence_Category" in csv_empty

        dirty_cells = [
            {"cell_id": "ID;with;semicolons", "status": "UNKNOWN\nNEWLINE", "confidence": 0.75, "confidence_category": "GREEN"},
        ]
        csv_dirty = generate_csv_data(dirty_cells)
        assert "Confidence" in csv_dirty


# =============================================================================
# 6. METRICS AGGREGATION ADVERSARIAL TESTS
# =============================================================================


class TestMetricsAggregationAdversarial:
    """Stress tests for metrics computation."""

    def test_metrics_large_scale_cell_list(self):
        """Compute metrics on 10,000 cells to verify speed and numerical precision."""
        np.random.seed(42)
        n = 10_000
        confs = np.random.uniform(0.0, 1.0, n)
        cell_list = []
        for i in range(n):
            c = float(confs[i])
            cell_list.append({
                "cell_id": i + 1,
                "area_px": 100.0 + i % 50,
                "circularity": 0.85,
                "confidence": c,
                "confidence_category": get_confidence_category(c),
            })

        summary = compute_summary_statistics(cell_list)
        assert summary["total_cells"] == n
        assert summary["uncertain_cells"] + summary["problematic_cells"] + summary["high_confidence_cells"] == n
        assert 0.0 <= summary["mean_confidence"] <= 1.0


# =============================================================================
# 7. MONTE CARLO RANDOMIZED FUZZING HARNESS
# =============================================================================


class TestMonteCarloRandomizedFuzzing:
    """Randomized fuzz testing with arbitrary image dimensions, noises, and synthetic shapes."""

    @pytest.mark.parametrize("seed", list(range(10)))
    def test_fuzz_calibration_and_confidence(self, seed):
        """Generate random noisy images with arbitrary circles and check stability."""
        rng = np.random.RandomState(seed)
        h = rng.randint(40, 300)
        w = rng.randint(40, 300)

        # Base noise
        img = rng.randint(0, 256, (h, w), dtype=np.uint8)

        # Draw 1-10 random synthetic circles / blobs
        num_blobs = rng.randint(1, 10)
        for _ in range(num_blobs):
            bx = rng.randint(10, w - 10)
            by = rng.randint(10, h - 10)
            br = rng.randint(3, 25)
            bval = rng.randint(0, 256)
            cv2.circle(img, (bx, by), br, bval, -1)

        # Calibration
        calibrated, stats = auto_calibrate_parameters(img)
        assert BOUNDS_CLAHE_CLIP[0] <= calibrated["clahe_clip_limit"] <= BOUNDS_CLAHE_CLIP[1]

        # Segmentation & Confidence
        cells, markers, _ = segment_cells(img, calibrated)
        for c in cells:
            assert 0.0 <= c["confidence"] <= 1.0
            assert c["confidence_category"] in ["GREEN", "YELLOW", "RED"]

        # Summary
        summary = compute_summary_statistics(cells)
        assert summary["total_cells"] == len(cells)
