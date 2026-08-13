"""Hauptseite für CellCounter Pro (Streamlit Web-UI).

Führt Bildanalyse, Watershed-Segmentierung, Viabilitätsbestimmung,
Sample-Galerie ("Probezellbilder"), Plotly-Grafiken und Datenexport zusammen.
"""

import os
import sys

# Füge Root-Verzeichnis zum PYTHONPATH hinzu
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import cv2
import numpy as np
import pandas as pd
import streamlit as st

from src.core.metrics import compute_summary_statistics
from src.core.preprocessing import (
    apply_clahe,
    denoise_image,
    downscale_image_if_needed,
    to_grayscale,
)
from src.core.segmentation import segment_cells
from src.core.tiff_handler import load_image_with_metadata
from src.core.viability import classify_viability
from src.ui.components import render_sidebar
from src.ui.visualization import (
    plot_intensity_scatter,
    plot_size_distribution,
    plot_viability_donut,
)
from src.utils.config_manager import load_config
from src.utils.database import (
    get_analysis_history,
    save_analysis_result,
)
from src.utils.io_export import create_annotated_overlay, generate_csv_data
from src.utils.logger import get_logger
from tests.generate_test_images import create_all_test_images

logger = get_logger("streamlit_app")


def main():
    st.set_page_config(
        page_title="CellCounter Pro - Bioinformatik Zellzählung",
        page_icon="🔬",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # 1. Konfiguration laden & Testbilder erzeugen (Probezellbilder)
    try:
        config = load_config("config.yaml")
        sample_files = create_all_test_images("tests/data")
    except Exception as err:
        st.error(f"Fehler beim Laden der Konfiguration/Testdaten: {err}")
        return

    # 2. Sidebar rendern
    seg_params, viab_params, active_preset = render_sidebar(config)

    # Header
    st.title("🔬 CellCounter Pro — Automated Microscopy Cell Counter")
    st.caption(f"Aktives Labor-Preset: **{active_preset}** | Modus: **Offline (Enhanced Peak Watershed Engine)**")

    # Tabs
    tab_analysis, tab_history, tab_support = st.tabs(
        ["📊 Bildanalyse & Zählung", "📜 Analyse-Historie (SQLite)", "🛠️ System & Support-Logs"]
    )

    # TAB 1: BILDANALYSE
    with tab_analysis:
        st.subheader("🖼️ Bildquelle auswählen")
        input_source_mode = st.radio(
            "Wähle den Bild-Eingabe-Modus:",
            options=["📁 Probezellbild aus Galerie wählen", "📤 Eigenes Mikroskopiebild hochladen"],
            horizontal=True,
        )

        file_bytes = None
        filename = "image"

        if input_source_mode == "📁 Probezellbild aus Galerie wählen":
            sample_options = {
                "1. Sauberes Testbild mit Zell-Clustern": "tests/data/synthetic_clean_cluster.png",
                "2. Testbild mit Vignettierung & Gradient": "tests/data/synthetic_vignetting_gradient.png",
                "3. Testbild mit Staubpartikeln & Rauschen": "tests/data/synthetic_dust_artifacts.png",
                "4. 16-Bit TIFF Mikroskopiebild": "tests/data/synthetic_16bit_microscopy.tiff",
            }
            selected_sample_key = st.selectbox(
                "Wähle ein Probezellbild für den Testdurchlauf:",
                options=list(sample_options.keys()),
            )
            sample_path = sample_options[selected_sample_key]
            filename = os.path.basename(sample_path)

            if os.path.exists(sample_path):
                with open(sample_path, "rb") as f:
                    file_bytes = f.read()
            else:
                st.warning(f"Probezellbild unter '{sample_path}' nicht gefunden.")

        else:
            uploaded_file = st.file_uploader(
                "Lade ein Mikroskopiebild hoch (JPEG, PNG, TIFF, 16-Bit):",
                type=["png", "jpg", "jpeg", "tif", "tiff"],
                help="Unterstützt Standard-Bilder sowie 16-Bit Mikroskopie-TIFFs.",
            )
            if uploaded_file is not None:
                file_bytes = uploaded_file.read()
                filename = uploaded_file.name

        # Analyse ausführen, wenn ein Bild geladen ist
        if file_bytes is not None:
            with st.spinner(f"Verarbeite Bild '{filename}' mit Enhanced Peak Watershed..."):
                try:
                    # a) Bild laden & Metadaten
                    img_raw, metadata = load_image_with_metadata(file_bytes, filename)
                    um_per_px = seg_params.get("um_per_pixel") or metadata.get("um_per_pixel")

                    # b) Graustufen & Vorverarbeitung
                    gray_orig = to_grayscale(img_raw)

                    # c) Downscaling für High-Res Bilder (> 4K)
                    gray_work, scale_factor = downscale_image_if_needed(
                        gray_orig, max_dimension=seg_params.get("max_dimension", 2048)
                    )

                    # d) Preprocessing (CLAHE + Entrauschung)
                    clahe = apply_clahe(gray_work)
                    denoised = denoise_image(clahe)

                    # e) Enhanced Peak Watershed Segmentierung
                    cell_list, markers, binary = segment_cells(
                        denoised, seg_params, scale_factor=scale_factor, um_per_pixel=um_per_px
                    )

                    # f) Lebend/Tot Viabilität
                    cell_list, viab_summary = classify_viability(
                        denoised, cell_list, viab_params
                    )

                    # g) Gesamte Metriken
                    summary = compute_summary_statistics(cell_list, viab_summary)

                    # h) High-Res Overlay zeichnen
                    annotated_img = create_annotated_overlay(
                        img_raw, cell_list, show_labels=True, show_contours=True
                    )

                except Exception as exc:
                    st.error(f"Fehler bei der Bildanalyse: {exc}")
                    logger.exception("Fehler während der Bildverarbeitung")
                    return

            st.success(f"Analyse von '{filename}' erfolgreich abgeschlossen!")

            # Metric-Cards
            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            col_m1.metric("Gesamtzahl Zellen", summary["total_cells"])
            col_m2.metric("Lebende Zellen", summary["live_cells"], delta=f"{summary['viability_pct']}% Viabilität")
            col_m3.metric("Tote Zellen", summary["dead_cells"])
            col_m4.metric(
                "Ø Zellfläche",
                f"{summary['mean_area_um2']} µm²" if summary["mean_area_um2"] else f"{summary['mean_area_px']} px²",
            )

            st.markdown("---")

            # Dual-Panel Bildvergleich
            st.subheader("🖼️ Bildanalyse Dual-Panel")
            col_img1, col_img2 = st.columns(2)

            with col_img1:
                st.image(img_raw, caption=f"Originalbild: {filename} ({img_raw.shape[1]}x{img_raw.shape[0]} px)")

            with col_img2:
                st.image(
                    annotated_img,
                    caption="Annotiertes Segmentierungsergebnis (Grün = Lebend, Rot = Tot)",
                )

            st.markdown("---")

            # Diagramme & Statistik
            st.subheader("📈 Zytometrische Auswertung")
            col_c1, col_c2, col_c3 = st.columns(3)

            with col_c1:
                fig_donut = plot_viability_donut(summary["live_cells"], summary["dead_cells"])
                st.plotly_chart(fig_donut, use_container_width=True)

            with col_c2:
                fig_size = plot_size_distribution(cell_list)
                st.plotly_chart(fig_size, use_container_width=True)

            with col_c3:
                fig_scatter = plot_intensity_scatter(cell_list)
                st.plotly_chart(fig_scatter, use_container_width=True)

            st.markdown("---")

            # Export & Datenbank-Speicherung
            st.subheader("💾 Ergebnis-Export & Datenbank-Erfassung")
            col_ex1, col_ex2, col_ex3 = st.columns(3)

            csv_data = generate_csv_data(cell_list)

            with col_ex1:
                st.download_button(
                    label="📄 Detail-Messergebnisse (.CSV herunterladen)",
                    data=csv_data,
                    file_name=f"cell_count_{filename}.csv",
                    mime="text/csv",
                )

            with col_ex2:
                is_success, buf = cv2.imencode(".png", cv2.cvtColor(annotated_img, cv2.COLOR_BGR2RGB))
                if is_success:
                    st.download_button(
                        label="🖼️ Annotiertes Overlay (.PNG herunterladen)",
                        data=buf.tobytes(),
                        file_name=f"annotated_{filename}.png",
                        mime="image/png",
                    )

            with col_ex3:
                if st.button("🗄️ In SQLite-Datenbank speichern"):
                    try:
                        analysis_id = save_analysis_result(
                            filename=filename,
                            summary=summary,
                            cells=cell_list,
                            preset_name=active_preset,
                            db_path=config.get("database", {}).get("db_path", "data/cell_counter.db"),
                            check_same_thread=False,
                        )
                        st.success(f"Erfolgreich als Analyse #{analysis_id} in SQLite gespeichert!")
                    except Exception as db_err:
                        st.error(f"Fehler beim Speichern in SQLite: {db_err}")

        else:
            st.info("👆 Bitte wähle ein Probezellbild oder lade ein Mikroskopiebild hoch.")

    # TAB 2: HISTORIE
    with tab_history:
        st.subheader("📜 Historie durchgeführter Labor-Analysen")
        db_path = config.get("database", {}).get("db_path", "data/cell_counter.db")

        try:
            history = get_analysis_history(limit=50, db_path=db_path, check_same_thread=False)
            if history:
                df_hist = pd.DataFrame(history)
                st.dataframe(df_hist, use_container_width=True)
            else:
                st.info("Noch keine gespeicherten Analysen in der Datenbank vorhanden.")
        except Exception as h_err:
            st.error(f"Fehler beim Abrufen der Historie: {h_err}")

    # TAB 3: SUPPORT & LOGS
    with tab_support:
        st.subheader("🛠️ Systemstatus & Support-Logs")
        st.markdown(
            "Wenn im Labor unerwartete Zählfehler auftreten, kannst du hier das aktuelle Logfile "
            "herunterladen und an den Entwickler übermitteln."
        )

        log_file_path = config.get("logging", {}).get("log_file", "logs/cell_counter.log")
        if os.path.exists(log_file_path):
            with open(log_file_path, "r", encoding="utf-8") as f:
                log_text = f.read()

            st.download_button(
                label="📥 Support-Logfile herunterladen (cell_counter.log)",
                data=log_text,
                file_name="cell_counter.log",
                mime="text/plain",
            )
            with st.expander("Vorschau der letzten Log-Einträge"):
                st.code(log_text[-2000:], language="text")
        else:
            st.info("Noch keine Log-Datei vorhanden.")


if __name__ == "__main__":
    main()
