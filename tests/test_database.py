"""Unit-Tests für das SQLite-Datenbankmodul (Threading-Check & Persistence)."""

import os
import pytest
from src.utils.database import (
    get_analysis_history,
    init_db,
    save_analysis_result,
)


def test_database_creation_and_save(tmp_path):
    """Testet SQLite-Tabellenerstellung und Speicherung von Analysedaten."""
    db_file = os.path.join(tmp_path, "test_cell_counter.db")
    init_db(db_file, check_same_thread=False)

    assert os.path.exists(db_file)

    summary = {
        "total_cells": 15,
        "live_cells": 12,
        "dead_cells": 3,
        "viability_pct": 80.0,
    }
    cells = [
        {
            "cell_id": 1,
            "x_px": 50.0,
            "y_px": 50.0,
            "area_px": 200.0,
            "area_um2": 15.5,
            "circularity": 0.85,
            "intensity_diff": 5.2,
            "status": "LIVE",
        },
        {
            "cell_id": 2,
            "x_px": 120.0,
            "y_px": 100.0,
            "area_px": 180.0,
            "area_um2": 14.0,
            "circularity": 0.78,
            "intensity_diff": -15.4,
            "status": "DEAD",
        },
    ]

    analysis_id = save_analysis_result(
        "test_image.png",
        summary,
        cells,
        preset_name="Standard_Brightfield",
        db_path=db_file,
        check_same_thread=False,
    )

    assert analysis_id > 0

    history = get_analysis_history(limit=10, db_path=db_file, check_same_thread=False)
    assert len(history) == 1
    assert history[0]["filename"] == "test_image.png"
    assert history[0]["total_cells"] == 15
    assert history[0]["viability_pct"] == 80.0
