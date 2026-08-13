"""Konfigurations- und Preset-Manager für CellCounter Pro.

Ermöglicht das Laden, Speichern und Verwalten von YAML-basierten Voreinstellungen (Presets),
sodass Parameter direkt in der UI oder Konfigurationsdatei bearbeitet werden können.
"""

import os
from typing import Any, Dict, List, Optional
import yaml

from src.utils.logger import get_logger

logger = get_logger("config_manager")

DEFAULT_CONFIG_PATH = "config.yaml"


def load_config(config_path: str = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    """Lädt die Konfigurationsdatei im YAML-Format.

    Args:
        config_path: Pfad zur YAML-Datei.

    Returns:
        Dict[str, Any]: Geladene Konfigurationsdaten.

    Raises:
        FileNotFoundError: Wenn die Datei nicht existiert.
        yaml.YAMLError: Bei Syntaxfehlern im YAML.
    """
    if not os.path.exists(config_path):
        logger.error(f"Konfigurationsdatei nicht gefunden: {config_path}")
        raise FileNotFoundError(f"Konfigurationsdatei '{config_path}' existiert nicht.")

    try:
        with open(config_path, "r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
            logger.info(f"Konfiguration erfolgreich aus {config_path} geladen.")
            return data
    except yaml.YAMLError as exc:
        logger.error(f"Fehler beim Parsen der YAML-Datei {config_path}: {exc}")
        raise


def save_config(config_data: Dict[str, Any], config_path: str = DEFAULT_CONFIG_PATH) -> bool:
    """Speichert die übergebenen Konfigurationsdaten in einer YAML-Datei.

    Args:
        config_data: Wörterbuch mit Konfigurationsdaten.
        config_path: Zielpfad für die YAML-Datei.

    Returns:
        bool: True bei Erfolg, False bei Fehler.
    """
    try:
        os.makedirs(os.path.dirname(os.path.abspath(config_path)), exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as file:
            yaml.safe_dump(config_data, file, default_flow_style=False, allow_unicode=True)
        logger.info(f"Konfiguration erfolgreich in {config_path} gespeichert.")
        return True
    except (OSError, yaml.YAMLError) as exc:
        logger.error(f"Fehler beim Speichern der Konfiguration in {config_path}: {exc}")
        return False


def get_available_presets(config_data: Optional[Dict[str, Any]] = None, config_path: str = DEFAULT_CONFIG_PATH) -> List[str]:
    """Gibt eine Liste aller verfügbaren Preset-Namen zurück.

    Args:
        config_data: Optionale bereits geladene Konfiguration.
        config_path: Pfad zur YAML-Datei, falls config_data None ist.

    Returns:
        List[str]: Liste der Preset-Namen.
    """
    if config_data is None:
        config_data = load_config(config_path)

    presets = config_data.get("presets", {})
    return list(presets.keys())


def get_preset(preset_name: str, config_data: Optional[Dict[str, Any]] = None, config_path: str = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    """Liefert die Parameter eines spezifischen Presets zurück.

    Args:
        preset_name: Name des Presets.
        config_data: Optionale bereits geladene Konfiguration.
        config_path: Pfad zur YAML-Datei, falls config_data None ist.

    Returns:
        Dict[str, Any]: Parameter des Presets.

    Raises:
        KeyError: Wenn das Preset nicht existiert.
    """
    if config_data is None:
        config_data = load_config(config_path)

    presets = config_data.get("presets", {})
    if preset_name not in presets:
        logger.warning(f"Preset '{preset_name}' nicht gefunden. Verwende Standardwerte.")
        if presets:
            first_key = list(presets.keys())[0]
            return presets[first_key]
        raise KeyError(f"Preset '{preset_name}' existiert nicht in der Konfiguration.")

    return presets[preset_name]


def save_preset(preset_name: str, preset_data: Dict[str, Any], config_path: str = DEFAULT_CONFIG_PATH) -> bool:
    """Speichert oder aktualisiert ein spezifisches Preset in der YAML-Konfiguration.

    Args:
        preset_name: Name des Presets.
        preset_data: Parameter des Presets.
        config_path: Pfad zur YAML-Datei.

    Returns:
        bool: True bei Erfolg, False bei Fehler.
    """
    try:
        config_data = load_config(config_path)
    except FileNotFoundError:
        config_data = {"presets": {}}

    if "presets" not in config_data:
        config_data["presets"] = {}

    config_data["presets"][preset_name] = preset_data
    return save_config(config_data, config_path)
