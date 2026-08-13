"""Database-Modul für CellCounter Pro (SQLite).

Speichert Analysedaten (Zellzahl, Viabilität, Einzelzell-Metriken) ab,
sodass spätere Serien-Analysen (Batch Processing) und Historien-Vergleiche möglich sind.
Enthält 'check_same_thread=False' für Streamlit-Thread-Sicherheit.
"""

import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from src.utils.logger import get_logger

logger = get_logger("database")

DEFAULT_DB_PATH = "data/cell_counter.db"


def get_connection(db_path: str = DEFAULT_DB_PATH, check_same_thread: bool = False) -> sqlite3.Connection:
    """Erstellt eine SQLite-Verbindung mit Thread-Sicherheitseinstellungen.

    Args:
        db_path: Pfad zur SQLite-Datenbankdatei.
        check_same_thread: Wenn False, kann die Verbindung in mehreren Threads (Streamlit) genutzt werden.

    Returns:
        sqlite3.Connection: Verbindung zur Datenbank.
    """
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(db_path, check_same_thread=check_same_thread)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: str = DEFAULT_DB_PATH, check_same_thread: bool = False) -> None:
    """Initialisiert das Datenbankschema (Tabellen 'analyses' und 'cells').

    Args:
        db_path: Pfad zur SQLite-Datenbankdatei.
        check_same_thread: SQLite-Threading-Einstellung.
    """
    conn = get_connection(db_path, check_same_thread=check_same_thread)
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS analyses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    filename TEXT NOT NULL,
                    total_cells INTEGER NOT NULL,
                    live_cells INTEGER NOT NULL,
                    dead_cells INTEGER NOT NULL,
                    viability_pct REAL NOT NULL,
                    preset_name TEXT
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cells (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    analysis_id INTEGER NOT NULL,
                    cell_id INTEGER NOT NULL,
                    x_px REAL NOT NULL,
                    y_px REAL NOT NULL,
                    area_px REAL NOT NULL,
                    area_um2 REAL,
                    circularity REAL NOT NULL,
                    intensity_diff REAL NOT NULL,
                    status TEXT NOT NULL,
                    FOREIGN KEY (analysis_id) REFERENCES analyses (id) ON DELETE CASCADE
                );
                """
            )
        logger.info(f"SQLite-Datenbank unter '{db_path}' erfolgreich initialisiert.")
    except sqlite3.Error as err:
        logger.error(f"Fehler bei der Datenbank-Initialisierung: {err}")
        raise
    finally:
        conn.close()


def save_analysis_result(
    filename: str,
    summary: Dict[str, Any],
    cells: List[Dict[str, Any]],
    preset_name: str = "",
    db_path: str = DEFAULT_DB_PATH,
    check_same_thread: bool = False,
) -> int:
    """Speichert ein neues Analyseergebnis mitsamt aller Einzelzellmessungen.

    Args:
        filename: Name der analysierten Bilddatei.
        summary: Wörterbuch mit Gesamtzahl, Viabilität etc.
        cells: Liste von Wörterbüchern mit Einzelzelldaten.
        preset_name: Verwendeter Preset-Name.
        db_path: Pfad zur SQLite-Datenbank.
        check_same_thread: SQLite-Threading-Einstellung.

    Returns:
        int: Generierte Analysis ID.
    """
    init_db(db_path, check_same_thread)
    conn = get_connection(db_path, check_same_thread=check_same_thread)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO analyses (filename, total_cells, live_cells, dead_cells, viability_pct, preset_name)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    filename,
                    int(summary.get("total_cells", 0)),
                    int(summary.get("live_cells", 0)),
                    int(summary.get("dead_cells", 0)),
                    float(summary.get("viability_pct", 0.0)),
                    preset_name,
                ),
            )
            analysis_id = cursor.lastrowid

            cell_records = [
                (
                    analysis_id,
                    int(c.get("cell_id", idx + 1)),
                    float(c.get("x_px", 0.0)),
                    float(c.get("y_px", 0.0)),
                    float(c.get("area_px", 0.0)),
                    float(c["area_um2"]) if c.get("area_um2") is not None else None,
                    float(c.get("circularity", 0.0)),
                    float(c.get("intensity_diff", 0.0)),
                    str(c.get("status", "UNKNOWN")),
                )
                for idx, c in enumerate(cells)
            ]

            cursor.executemany(
                """
                INSERT INTO cells (analysis_id, cell_id, x_px, y_px, area_px, area_um2, circularity, intensity_diff, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                cell_records,
            )

        logger.info(f"Analyse #{analysis_id} für '{filename}' mit {len(cells)} Zellen in DB gespeichert.")
        return analysis_id
    except sqlite3.Error as err:
        logger.error(f"Fehler beim Speichern der Analyse in SQLite: {err}")
        raise
    finally:
        conn.close()


def get_analysis_history(
    limit: int = 50, db_path: str = DEFAULT_DB_PATH, check_same_thread: bool = False
) -> List[Dict[str, Any]]:
    """Ruft die Historie der durchgeführten Analysen ab.

    Args:
        limit: Maximale Anzahl abzurufender Datensätze.
        db_path: Pfad zur Datenbank.
        check_same_thread: SQLite-Threading-Einstellung.

    Returns:
        List[Dict[str, Any]]: Liste der Analysen.
    """
    init_db(db_path, check_same_thread)
    conn = get_connection(db_path, check_same_thread=check_same_thread)
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, timestamp, filename, total_cells, live_cells, dead_cells, viability_pct, preset_name
            FROM analyses
            ORDER BY id DESC
            LIMIT ?;
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error as err:
        logger.error(f"Fehler beim Abrufen der Analyse-Historie: {err}")
        return []
    finally:
        conn.close()
