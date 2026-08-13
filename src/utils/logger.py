"""Logging-Modul für CellCounter Pro.

Stellt eine zentrale Logging-Konfiguration mit rotierenden Log-Dateien bereit,
sodass Laboranten im Fehlerfall Diagnoseberichte exportieren können.
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional


def setup_logger(
    name: str = "cell_counter",
    log_file: str = "logs/cell_counter.log",
    level: int = logging.INFO,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
) -> logging.Logger:
    """Richtet den Anwendung-Logger mit Datei- und Konsolenausgabe ein.

    Args:
        name: Name des Loggers.
        log_file: Pfad zur Log-Datei.
        level: Logging-Level (z.B. logging.INFO oder logging.DEBUG).
        max_bytes: Maximale Dateigröße in Bytes vor der Rotation.
        backup_count: Anzahl der aufzubewahrenden alten Log-Dateien.

    Returns:
        logging.Logger: Konfigurierte Logger-Instanz.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Konsolen-Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Rotierender Datei-Handler
    try:
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except (OSError, PermissionError) as err:
        logger.warning(f"Datei-Logging konnte nicht initialisiert werden ({err}). Nutze Konsolen-Logging.")

    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Liefert die zentrale Logger-Instanz zurück.

    Args:
        name: Optionaler Untername für den Logger.

    Returns:
        logging.Logger: Logger-Instanz.
    """
    base_logger = setup_logger()
    if name:
        return base_logger.getChild(name)
    return base_logger
