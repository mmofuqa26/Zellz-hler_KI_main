<div align="center">

# 🔬 CellCounter Pro

**Automatische Zellzählung aus Hellfeldmikroskopie-Bildern**  
*Offline-fähig · Labor-tauglich · Open Source*

[![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.28+-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![OpenCV](https://img.shields.io/badge/OpenCV-4.8+-5C3EE8?logo=opencv&logoColor=white)](https://opencv.org/)
[![Tests](https://img.shields.io/badge/Tests-10%2F10%20passing-brightgreen?logo=pytest)](tests/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

</div>

---

## ✨ Features

| Feature | Details |
|---|---|
| 🧩 **Enhanced Peak Watershed** | Lokale-Maxima-Detektion für präzises Cluster-Splitting berührender Zellen |
| 🩺 **Lebend/Tot-Analyse** | Lokale Hintergrundsubtraktion ($\Delta I = I_{core} - I_{ring}$) für Trypanblau-Auswertung |
| 🖼️ **TIFF 16-Bit Support** | Automatische Perzentil-Normalisierung, Z-Stack Max-Intensity-Projection, µm/px Metadaten |
| ⚡ **High-Res Performance** | Automatisches Downscaling bis 50 Megapixel (Koordinaten werden exakt zurückskaliert) |
| ⚙️ **YAML Preset-Manager** | Laborparameter (Zelllinie, Farbstoff) als benannte Presets speicherbar direkt aus der UI |
| 🗄️ **SQLite Historie** | Alle Analysen mit Einzelzell-Metriken werden in einer lokalen Datenbank gespeichert |
| 📜 **Rotating Logs** | `logs/cell_counter.log` für Support-Diagnose — Ein-Klick-Download aus der UI |
| 📤 **Export** | CSV-Messdaten + hochauflösendes annotiertes Overlay-Bild (.PNG) |

---

## 🖥️ Screenshots

### Streamlit Web-UI — Dual-Panel Analyse

```
┌─────────────────────────────────────────────────────────┐
│  Originalbild              │  Annotiertes Overlay       │
│  (Hellfeldmikroskopie)     │  Grün = Lebend ●           │
│                            │  Rot   = Tot   ●           │
│                            │  Zell-IDs eingeblendet     │
└─────────────────────────────────────────────────────────┘
│  Gesamtzahl  │  Lebend  │  Tot  │  Ø Zellfläche         │
│  Donut-Chart │  Größen-Histogramm  │  Intensität-Scatter │
└─────────────────────────────────────────────────────────┘
```

---

## 🚀 Schnellstart

### 1. Voraussetzungen
- Windows / macOS / Linux
- [uv](https://github.com/astral-sh/uv) (empfohlen) oder pip

### 2. Installation

```bash
# Repository klonen
git clone https://github.com/mmofuqa26/Zellz-hler_KI_main.git
cd Zellz-hler_KI_main

# Virtuelle Umgebung mit uv erstellen und Pakete installieren
uv venv --python 3.11
uv pip install -r requirements.txt
```

### 3. Starten

```bash
# Streamlit Web-UI starten
.venv\Scripts\streamlit run src/ui/app.py        # Windows
.venv/bin/streamlit run src/ui/app.py             # macOS/Linux
```

Öffne dann im Browser: **http://localhost:8501**

---

## 📁 Projektstruktur

```
CellCounter Pro/
├── config.yaml                  # Zentrale Konfiguration & Labor-Presets
├── requirements.txt
├── src/
│   ├── core/
│   │   ├── preprocessing.py     # CLAHE, Downscaling, Flatfield-Korrektur
│   │   ├── segmentation.py      # Enhanced Peak Watershed
│   │   ├── viability.py         # Lebend/Tot (I_core vs. I_ring)
│   │   ├── tiff_handler.py      # 16-Bit TIFF, Z-Stacks, µm-Metadaten
│   │   └── metrics.py           # Statistik & Größenverteilung
│   ├── ui/
│   │   ├── app.py               # Streamlit Hauptseite
│   │   ├── components.py        # Sidebar, Preset-Manager, Parameter-Regler
│   │   └── visualization.py     # Plotly Charts
│   └── utils/
│       ├── config_manager.py    # YAML Preset-Verwaltung
│       ├── database.py          # SQLite (analyses & cells Tabellen)
│       ├── logger.py            # Rotating Log-Handler
│       └── io_export.py         # CSV & PNG Export
└── tests/
    ├── generate_test_images.py  # Synthetische Bilder (Vignettierung, Staub, 16-Bit)
    ├── test_preprocessing.py
    ├── test_segmentation.py
    ├── test_viability.py
    ├── test_tiff.py
    └── test_database.py
```

---

## ⚙️ Konfiguration & Presets

Die Datei `config.yaml` enthält vordefinierte Presets für gängige Laboranwendungen:

| Preset | Anwendungsfall |
|---|---|
| `Standard_Brightfield` | Allgemeine Zellkulturen (HEK293, HeLa, CHO) |
| `Trypan_Blue_Viability` | Trypanblau-Farbausschluss-Test (Lebend/Tot-Zählung) |
| `High_Density_Yeast` | Dichte Hefe-Kulturen oder kleine Suspensionszellen |

Presets können direkt aus der Streamlit-UI gespeichert werden — **kein Python-Wissen erforderlich**.

---

## 🧪 Tests ausführen

```bash
.venv\Scripts\python -m pytest -v     # Windows
.venv/bin/python -m pytest -v          # macOS/Linux
```

**Ergebnis:** `10 passed` ✅

Die Tests validieren automatisch:
- Vorverarbeitung (CLAHE, Downscaling, Rauschunterdrückung)
- Watershed-Segmentierung auf sauberen und verrauschten Bildern
- Lebend/Tot-Klassifizierung (Viabilität)
- 16-Bit TIFF-Import & Normalisierung
- SQLite-Datenbankoperationen (Thread-Sicherheit)

---

## 📐 Algorithmus-Übersicht

```
Bild (JPEG/PNG/TIFF)
        │
        ▼
Vorverarbeitung
  ├─ 16-Bit → 8-Bit Normalisierung (Perzentil-basiert)
  ├─ Downscaling bei > 4K Auflösung
  ├─ CLAHE (lokale Kontrastkorrektur)
  └─ Gauß-Entrauschung
        │
        ▼
Segmentierung (Enhanced Peak Watershed)
  ├─ Adaptives Thresholding + Otsu
  ├─ Morphologisches Schließen & Hole-Filling
  ├─ Euklidische Distanztransformation
  ├─ Lokale-Maxima-Detektion (Cluster-Splitting)
  └─ Marker-Filterung (min_marker_area_px)
        │
        ▼
Viabilitätsanalyse
  ├─ I_core (Zellkern-Intensität)
  ├─ I_ring (lokaler Hintergrundring)
  └─ ΔI = I_core - I_ring → LIVE / DEAD
        │
        ▼
Export
  ├─ Annotiertes Overlay (.PNG)
  ├─ CSV-Messdaten (Fläche, Zirkularität, Status)
  └─ SQLite-Datenbank (Analyse-Historie)
```

---

## 🤝 Beitragen

Pull Requests und Issues sind willkommen!

1. Fork das Repository
2. Erstelle einen Feature-Branch (`git checkout -b feature/mein-feature`)
3. Commit deine Änderungen (`git commit -m "feat: Beschreibung"`)
4. Push zum Branch (`git push origin feature/mein-feature`)
5. Öffne einen Pull Request

---

## 📄 Lizenz

MIT License — frei nutzbar für Forschung und Labor-Anwendungen.

---

<div align="center">

Entwickelt mit ❤️ für den Labor-Alltag · Offline-fähig · Keine Cloud erforderlich

</div>
