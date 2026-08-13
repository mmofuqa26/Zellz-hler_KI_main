# GEMINI.md – Zellzählungsprojekt

## Tech-Stack
- Python 3.11+ mit Typ-Hints (typing)
- OpenCV für Bildverarbeitung
- NumPy für Array-Operationen
- Streamlit für die Web-UI
- Plotly für Visualisierungen
- Pytest für Tests

## Code-Standards
- Alle Funktionen müssen Docstrings (Google-Stil) haben
- Keine bare `except:` – immer spezifische Exceptions
- Keine Hardcoded Pfade – alles über Config oder CLI-Args
- Logging statt print() verwenden
- PEP 8 konform

## Test-Strategie
- Jede Bildverarbeitungsfunktion braucht Unit-Tests
- Mindestens 3 Testbilder (synthetisch) im /tests/data Ordner
- Vor jeder Änderung: Tests laufen lassen

## Architektur
- Trennung: Core (Bildverarbeitung) | UI (Streamlit) | Utils (Hilfsfunktionen)
- Keine Business-Logik in der UI-Schicht