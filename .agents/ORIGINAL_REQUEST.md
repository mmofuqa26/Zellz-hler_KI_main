# Original User Request

## 2026-08-31T21:03:39Z

CellCounter Pro soll mit drei konkreten Erweiterungen deutlich praxistauglicher werden: automatische Bild-Kalibrierung, visuelle Konfidenz-Markierungen und eine einfache manuelle Korrektur-UI. Das Projekt baut auf dem bestehenden Python/Streamlit-Codebase auf.

Working directory: c:/Users/miran/Documents/Zellzählerki/antigravity

## Requirements

### R1. Automatische Parameter-Kalibrierung pro Bild
Vor der Segmentierung wird jedes Bild statistisch analysiert (Histogramm-Verteilung, lokaler Kontrast, Helligkeitsgradient). Basierend darauf werden die Watershed-Parameter (Schwellenwert, CLAHE-Clip-Limit, Mindest-Markerflaeche, Distanz-Ratio) automatisch angepasst, ohne dass der Nutzer die Slider manuell bewegen muss. Die manuellen Slider in der Sidebar bleiben als Override erhalten.

### R2. Konfidenz-Ampel pro Zell-Region
Jede segmentierte Zelle erhaelt einen Konfidenz-Score (0 bis 1) basierend auf Zirkularitaet, Soliditaet und lokalem Kontrast-zu-Rauschen-Verhaeltnis. Im annotierten Overlay-Bild werden Zellen farblich markiert: Gruen (sicher >= 0.7), Gelb (unsicher 0.4 bis 0.7), Rot (wahrscheinlich falsch < 0.4). Die Anzahl unsicherer/roter Zellen wird prominent in den Metriken angezeigt.

### R3. Manuelle Korrektur-UI
Unterhalb des Dual-Panels erscheint ein einfacher Korrektur-Bereich: Ein Zahlen-Eingabefeld 'Korrigierte Gesamtzahl' (pre-filled mit dem Algorithmus-Ergebnis). Ein Button 'Korrektur speichern' speichert das Originalbild zusammen mit den finalen Marker-Koordinaten und dem Korrektur-Delta als JSON in data/corrections/ fuer spaeteres Modell-Training. Die Edit-Funktion soll einfach und schnell bedienbar sein; komplexes Polygon-Editing ist nicht erforderlich.

## Acceptance Criteria

### Kalibrierung
- Bei 3 Testbildern unterschiedlicher Beleuchtung (aus tests/data/) liefert die Auto-Kalibrierung ohne manuellen Eingriff mindestens so viele erkannte Zellen wie die bisherige feste Konfiguration.
- Kalibrierungs-Parameter werden im Log mit INFO-Level ausgegeben.

### Konfidenz-Ampel
- Jede Zelle im Overlay hat eine der drei Farben (Gruen/Gelb/Rot).
- Die Metrik-Zeile zeigt 'Unsichere Zellen: X' und 'Problematische Regionen: Y' zusaetzlich zu Gesamtzahl und Viabilitaet.
- Die Konfidenz-Werte werden im CSV-Export als Spalte 'confidence' ausgegeben.

### Korrektur-UI
- Der Nutzer kann die Zahl manuell ueberschreiben und speichern.
- Jede gespeicherte Korrektur erzeugt eine Datei in data/corrections/<timestamp>_<filename>.json mit den Feldern: original_count, corrected_count, delta, markers, image_path.

### Tests
- Alle bestehenden 10 Pytest-Tests laufen weiterhin durch (pytest -v).
- Mindestens 2 neue Unit-Tests fuer den Konfidenz-Score und die Auto-Kalibrierung werden hinzugefuegt.
