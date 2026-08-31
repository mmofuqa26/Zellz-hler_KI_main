"""Unit-Tests für das Manual Correction Storage & Persistence Modul (R3).

Testet:
1. JSON-Struktur und Pflichtfelder (original_count, corrected_count, delta, markers, image_path, timestamp)
2. Automatische Verzeichniserstellung bei noch nicht existierenden Zielpfaden
3. Serialisierung von NumPy-Datentypen (np.int64, np.float32, np.bool_, np.ndarray) ohne Typfehler
4. Korrekte Delta-Berechnung (positiv, negativ, null)
5. Dateinamenbereinigung und Fallback-Verhalten
6. Logging auf INFO-Ebene bei erfolgreicher Speicherung
7. Validierung ungültiger Eingaben (ValueError)
"""

import json
import logging
import os
import numpy as np
import pytest

from src.utils.io_export import save_manual_correction


def test_save_manual_correction_json_structure(tmp_path):
    """Überprüft, ob alle Pflichtfelder in der JSON-Datei enthalten sind und korrekte Werte haben."""
    out_dir = str(tmp_path / "corrections")
    sample_cells = [
        {
            "cell_id": 1,
            "x_px": 100.5,
            "y_px": 200.25,
            "area_px": 350.0,
            "confidence": 0.85,
            "status": "LIVE",
        },
        {
            "cell_id": 2,
            "x_px": 150.0,
            "y_px": 250.0,
            "area_px": 420.0,
            "confidence": 0.45,
            "status": "DEAD",
        },
    ]

    saved_path = save_manual_correction(
        filename="test_microscopy.png",
        original_count=2,
        corrected_count=3,
        cell_list=sample_cells,
        image_path="/path/to/test_microscopy.png",
        output_dir=out_dir,
    )

    assert os.path.exists(saved_path)
    assert saved_path.endswith("_test_microscopy.json")

    with open(saved_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Pflichtfelder prüfen
    assert "original_count" in data
    assert "corrected_count" in data
    assert "delta" in data
    assert "markers" in data
    assert "image_path" in data
    assert "timestamp" in data

    # Feldwerte prüfen
    assert data["original_count"] == 2
    assert data["corrected_count"] == 3
    assert data["delta"] == 1
    assert data["image_path"] == "/path/to/test_microscopy.png"
    assert isinstance(data["timestamp"], str)
    assert len(data["timestamp"]) > 0

    # Marker prüfen
    assert len(data["markers"]) == 2
    m1 = data["markers"][0]
    assert m1["cell_id"] == 1
    assert pytest.approx(m1["x_px"]) == 100.5
    assert pytest.approx(m1["y_px"]) == 200.25
    assert pytest.approx(m1["area_px"]) == 350.0
    assert pytest.approx(m1["confidence"]) == 0.85
    assert m1["status"] == "LIVE"


def test_save_manual_correction_directory_creation(tmp_path):
    """Überprüft, dass fehlende Zielverzeichnisse (inkl. verschachtelter Pfade) automatisch erstellt werden."""
    nested_dir = str(tmp_path / "deeply" / "nested" / "corrections_dir")
    assert not os.path.exists(nested_dir)

    saved_path = save_manual_correction(
        filename="sample_image.tif",
        original_count=10,
        corrected_count=12,
        cell_list=[],
        output_dir=nested_dir,
    )

    assert os.path.exists(nested_dir)
    assert os.path.isfile(saved_path)
    assert os.path.dirname(saved_path) == nested_dir


def test_save_manual_correction_numpy_types(tmp_path):
    """Überprüft, dass NumPy-Skalare (np.float32, np.int64, np.bool_) fehlerfrei serialisiert werden."""
    out_dir = str(tmp_path / "numpy_test")
    numpy_cells = [
        {
            "cell_id": np.int64(42),
            "x_px": np.float32(123.456),
            "y_px": np.float64(789.012),
            "area_px": np.int32(500),
            "confidence": np.float32(0.92),
            "status": "LIVE",
            "is_valid": np.bool_(True),
            "raw_vector": np.array([1, 2, 3]),
        }
    ]

    saved_path = save_manual_correction(
        filename="numpy_sample.png",
        original_count=np.int64(1),
        corrected_count=np.int32(1),
        cell_list=numpy_cells,
        output_dir=out_dir,
    )

    assert os.path.exists(saved_path)

    with open(saved_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert isinstance(data["original_count"], int)
    assert isinstance(data["corrected_count"], int)
    assert isinstance(data["delta"], int)
    assert isinstance(data["markers"][0]["x_px"], float)
    assert isinstance(data["markers"][0]["y_px"], float)
    assert isinstance(data["markers"][0]["area_px"], float)
    assert isinstance(data["markers"][0]["confidence"], float)
    assert isinstance(data["markers"][0]["cell_id"], int)


def test_save_manual_correction_delta_calculation(tmp_path):
    """Testet positive, negative und neutrale Deltas zwischen Korrektur und Algorithmus."""
    out_dir = str(tmp_path / "delta_test")

    # Positives Delta (Nutzer fügt Zellen hinzu)
    path_pos = save_manual_correction(
        filename="pos.png",
        original_count=15,
        corrected_count=20,
        cell_list=[],
        output_dir=out_dir,
    )
    with open(path_pos, "r", encoding="utf-8") as f:
        assert json.load(f)["delta"] == 5

    # Negatives Delta (Nutzer entfernt falsch-positive Zellen)
    path_neg = save_manual_correction(
        filename="neg.png",
        original_count=20,
        corrected_count=14,
        cell_list=[],
        output_dir=out_dir,
    )
    with open(path_neg, "r", encoding="utf-8") as f:
        assert json.load(f)["delta"] == -6

    # Null Delta (Keine Änderung)
    path_zero = save_manual_correction(
        filename="zero.png",
        original_count=10,
        corrected_count=10,
        cell_list=[],
        output_dir=out_dir,
    )
    with open(path_zero, "r", encoding="utf-8") as f:
        assert json.load(f)["delta"] == 0


def test_save_manual_correction_filename_sanitization_and_fallbacks(tmp_path):
    """Testet saubere Dateinamensbehandlung bei Pfaden, leeren Namen und Sonderfällen."""
    out_dir = str(tmp_path / "naming_test")

    # Pfad mit Unterverzeichnissen und Endung
    path1 = save_manual_correction(
        filename="/var/microscopy/subfolder/experiment_A.ome.tiff",
        original_count=5,
        corrected_count=5,
        cell_list=[],
        output_dir=out_dir,
    )
    assert "experiment_A.ome" in os.path.basename(path1)

    # Leerer Dateiname -> Fallback auf 'correction'
    path2 = save_manual_correction(
        filename="",
        original_count=0,
        corrected_count=0,
        cell_list=[],
        output_dir=out_dir,
    )
    assert "_correction.json" in os.path.basename(path2)


def test_save_manual_correction_logging(tmp_path, caplog):
    """Überprüft, ob beim Speichern ein INFO-Log-Eintrag erzeugt wird."""
    out_dir = str(tmp_path / "log_test")
    with caplog.at_level(logging.INFO):
        save_manual_correction(
            filename="logging_sample.png",
            original_count=5,
            corrected_count=8,
            cell_list=[],
            output_dir=out_dir,
        )

    assert any(
        "Manuelle Korrektur gespeichert" in rec.message and "Delta: +3" in rec.message
        for rec in caplog.records
    )


def test_save_manual_correction_invalid_inputs(tmp_path):
    """Überprüft, dass fehlerhafte Zählwerte mit ValueError abgelehnt werden."""
    out_dir = str(tmp_path / "invalid_test")

    with pytest.raises(ValueError):
        save_manual_correction(
            filename="invalid.png",
            original_count="not_a_number",  # type: ignore
            corrected_count=5,
            cell_list=[],
            output_dir=out_dir,
        )

    with pytest.raises(ValueError):
        save_manual_correction(
            filename="invalid.png",
            original_count=5,
            corrected_count="invalid",  # type: ignore
            cell_list=[],
            output_dir=out_dir,
        )
