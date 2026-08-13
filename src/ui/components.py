"""UI-Komponenten für CellCounter Pro.

Enthält die Konfigurations-Sidebar, Preset-Verwaltung, Schwellenwert-Regler
und Support-Export-Buttons.
"""

from typing import Any, Dict, Tuple
import streamlit as st

from src.utils.config_manager import (
    get_available_presets,
    get_preset,
    save_preset,
)
from src.utils.logger import get_logger

logger = get_logger("ui_components")


def render_sidebar(config_data: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], str]:
    """Rendert die Konfigurations-Sidebar in Streamlit.

    Args:
        config_data: Geladene YAML-Konfigurationsdaten.

    Returns:
        Tuple[Dict[str, Any], Dict[str, Any], str]:
            - Segmentierungsparameter
            - Viabilitätsparameter
            - Ausgewählter Preset-Name
    """
    st.sidebar.title("🔬 CellCounter Pro")
    st.sidebar.markdown("---")

    # 1. Preset-Auswahl
    st.sidebar.subheader("📋 Preset-Verwaltung")
    available_presets = get_available_presets(config_data)

    default_preset_name = config_data.get("default_preset", "Standard_Brightfield")
    default_idx = (
        available_presets.index(default_preset_name)
        if default_preset_name in available_presets
        else 0
    )

    selected_preset_name = st.sidebar.selectbox(
        "Wähle ein Labor-Preset:",
        options=available_presets,
        index=default_idx,
        help="Vordefinierte Einstellungen für spezifische Zelltypen oder Farbstoffe.",
    )

    preset = get_preset(selected_preset_name, config_data)
    seg_defaults = preset.get("segmentation", {})
    viab_defaults = preset.get("viability", {})
    prep_defaults = preset.get("preprocessing", {})

    st.sidebar.caption(preset.get("description", ""))

    st.sidebar.markdown("---")

    # 2. Segmentierungs-Parameter
    st.sidebar.subheader("🧩 Segmentierung & Cluster")

    min_diam, max_diam = st.sidebar.slider(
        "Zelldurchmesser (Pixel):",
        min_value=4,
        max_value=200,
        value=(
            int(seg_defaults.get("min_cell_diameter_px", 12)),
            int(seg_defaults.get("max_cell_diameter_px", 120)),
        ),
        step=2,
        help="Grenzen für die erwartete Zellgröße zur Artefaktfilterung.",
    )

    dist_ratio = st.sidebar.slider(
        "Cluster-Trennungs-Empfindlichkeit:",
        min_value=0.10,
        max_value=0.60,
        value=float(seg_defaults.get("dist_threshold_ratio", 0.25)),
        step=0.05,
        help="Niedriger -> Stärkere Trennung dicht verclusterter Zellen. Höher -> Konservativer.",
    )

    min_marker_area = st.sidebar.number_input(
        "Mindest-Markerfläche (Pixel):",
        min_value=1,
        max_value=50,
        value=int(seg_defaults.get("min_marker_area_px", 3)),
        help="Filtert winzige Falsch-Maxima heraus, um Übersegmentierung zu vermeiden.",
    )

    block_size = st.sidebar.slider(
        "Adaptiver Schwellenwert Blockgröße:",
        min_value=7,
        max_value=61,
        value=int(seg_defaults.get("adaptive_thresh_block_size", 21)),
        step=2,
    )

    min_circularity = st.sidebar.slider(
        "Mindest-Zirkularität (0-1):",
        min_value=0.10,
        max_value=0.90,
        value=float(seg_defaults.get("min_circularity", 0.35)),
        step=0.05,
        help="1.0 = Perfekter Kreis. Sortiert unregelmäßige Staubpartikel aus.",
    )

    st.sidebar.markdown("---")

    # 3. Viabilitäts-Parameter
    st.sidebar.subheader("🩺 Lebend / Tot Analyse")
    viab_enabled = st.sidebar.checkbox(
        "Trypanblau-Viabilität aktivieren",
        value=bool(viab_defaults.get("enabled", True)),
    )

    intensity_diff_thresh = st.sidebar.slider(
        "Schwellenwert Kontrast-Differenz (I_core - I_ring):",
        min_value=-50.0,
        max_value=10.0,
        value=float(viab_defaults.get("intensity_diff_threshold", -12.0)),
        step=1.0,
        help="Negativer -> Kern ist dunkler als der Rand (Trypanblau-Aufnahme).",
    )

    ring_width = st.sidebar.slider(
        "Lokale Hintergrund-Ringbreite (px):",
        min_value=2,
        max_value=15,
        value=int(viab_defaults.get("ring_width_px", 4)),
        step=1,
    )

    st.sidebar.markdown("---")

    # 4. Mikrometer-Skalierung
    st.sidebar.subheader("📏 Physikalische Skalierung")
    um_per_pixel = st.sidebar.number_input(
        "Auflösung (µm / Pixel):",
        min_value=0.0,
        max_value=100.0,
        value=0.0,
        step=0.1,
        help="0.0 = Aus. Falls angegeben, wird die Zellfläche in µm² umgerechnet.",
    )

    # Zusammenstellen der Parameter
    seg_params = {
        "min_cell_diameter_px": min_diam,
        "max_cell_diameter_px": max_diam,
        "adaptive_thresh_block_size": block_size,
        "adaptive_thresh_c": int(seg_defaults.get("adaptive_thresh_c", 5)),
        "min_marker_area_px": min_marker_area,
        "dist_threshold_ratio": dist_ratio,
        "min_circularity": min_circularity,
        "min_solidity": float(seg_defaults.get("min_solidity", 0.50)),
        "um_per_pixel": um_per_pixel if um_per_pixel > 0 else None,
        "max_dimension": int(prep_defaults.get("max_dimension", 2048)),
    }

    viab_params = {
        "enabled": viab_enabled,
        "ring_width_px": ring_width,
        "intensity_diff_threshold": intensity_diff_thresh,
    }

    # Preset Speichern Dialog in Sidebar
    st.sidebar.markdown("---")
    with st.sidebar.expander("💾 Neues Preset speichern"):
        new_preset_name = st.text_input("Preset-Name:", value="Mein_Labor_Preset")
        new_preset_desc = st.text_input("Beschreibung:", value="Eigene Parameter")
        if st.button("Preset in config.yaml speichern"):
            new_preset_data = {
                "description": new_preset_desc,
                "preprocessing": prep_defaults,
                "segmentation": seg_params,
                "viability": viab_params,
            }
            if save_preset(new_preset_name, new_preset_data):
                st.success(f"Preset '{new_preset_name}' gespeichert!")
                st.rerun()
            else:
                st.error("Fehler beim Speichern des Presets.")

    return seg_params, viab_params, selected_preset_name
