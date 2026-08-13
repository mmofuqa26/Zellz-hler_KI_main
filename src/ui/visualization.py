"""Visualisierungs-Modul für Streamlit (Plotly Charts & Interaktive Grafiken).

Bietet moderne, laborrelevante Diagramme für Viabilität (Donut-Chart),
Zellgrößen-Verteilung (Histogramm) und Relativ-Intensitäten (Scatter-Plot).
"""

from typing import Any, Dict, List
import numpy as np
import plotly.express as px
import plotly.graph_objects as go


def plot_viability_donut(live_cells: int, dead_cells: int) -> go.Figure:
    """Erzeugt ein modernes Donut-Diagramm für die Zell-Viabilität.

    Args:
        live_cells: Anzahl lebender Zellen.
        dead_cells: Anzahl toter Zellen.

    Returns:
        go.Figure: Plotly Figur.
    """
    total = live_cells + dead_cells
    viability_pct = (live_cells / total * 100.0) if total > 0 else 0.0

    labels = ["Lebend (Farbausschluss)", "Tot (Trypanblau)"]
    values = [live_cells, dead_cells]
    colors = ["#2ecc71", "#e74c3c"]

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.6,
                marker=dict(colors=colors, line=dict(color="#ffffff", width=2)),
                textinfo="percent+value",
                hoverinfo="label+value+percent",
            )
        ]
    )

    fig.update_layout(
        title=dict(text="Viabilitäts-Verhältnis", font=dict(size=18)),
        annotations=[
            dict(
                text=f"<b>{viability_pct:.1f}%</b><br>Viabilität",
                x=0.5,
                y=0.5,
                font_size=20,
                showarrow=False,
            )
        ],
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5),
        margin=dict(l=20, r=20, t=50, b=20),
        height=320,
    )
    return fig


def plot_size_distribution(cell_list: List[Dict[str, Any]]) -> go.Figure:
    """Erzeugt ein Histogramm der Zellgrößenverteilung.

    Args:
        cell_list: Liste aller segmentierten Zellen.

    Returns:
        go.Figure: Plotly Histogramm.
    """
    if not cell_list:
        fig = go.Figure()
        fig.update_layout(title="Keine Daten verfügbar")
        return fig

    has_um2 = any(c.get("area_um2") is not None for c in cell_list)
    if has_um2:
        values = [c["area_um2"] for c in cell_list if c.get("area_um2") is not None]
        x_label = "Zellfläche (µm²)"
    else:
        values = [c["area_px"] for c in cell_list]
        x_label = "Zellfläche (Pixel²)"

    fig = px.histogram(
        x=values,
        nbins=25,
        labels={"x": x_label, "y": "Anzahl Zellen"},
        title="Zellgrößen-Verteilung",
        color_discrete_sequence=["#3498db"],
        opacity=0.85,
    )

    fig.update_layout(
        xaxis_title=x_label,
        yaxis_title="Zellanzahl",
        bargap=0.08,
        margin=dict(l=20, r=20, t=50, b=20),
        height=320,
    )
    return fig


def plot_intensity_scatter(cell_list: List[Dict[str, Any]]) -> go.Figure:
    """Erzeugt ein Scatterplot der Kern- vs. Ring-Intensität zur Kontrolle des Lebend/Tot-Cutoffs.

    Args:
        cell_list: Liste der segmentierten Zellen.

    Returns:
        go.Figure: Plotly Scatterplot.
    """
    if not cell_list:
        fig = go.Figure()
        fig.update_layout(title="Keine Intensitätsdaten")
        return fig

    i_cores = [c.get("i_core", 0.0) for c in cell_list]
    i_rings = [c.get("i_ring", 0.0) for c in cell_list]
    statuses = [c.get("status", "LIVE") for c in cell_list]
    ids = [f"Zelle #{c.get('cell_id')}" for c in cell_list]

    fig = px.scatter(
        x=i_rings,
        y=i_cores,
        color=statuses,
        color_discrete_map={"LIVE": "#2ecc71", "DEAD": "#e74c3c"},
        hover_name=ids,
        labels={"x": "Lokaler Hintergrund I_ring", "y": "Kern-Intensität I_core"},
        title="Lebend/Tot-Kontrastverteilung (I_core vs. I_ring)",
    )

    # Diagonale Referenzlinie (I_core = I_ring)
    if i_rings and i_cores:
        max_val = max(max(i_rings), max(i_cores)) + 10
        fig.add_trace(
            go.Scatter(
                x=[0, max_val],
                y=[0, max_val],
                mode="lines",
                line=dict(color="gray", dash="dash"),
                name="Gleichheitslinie (I_core = I_ring)",
            )
        )

    fig.update_layout(
        margin=dict(l=20, r=20, t=50, b=20),
        height=320,
    )
    return fig
