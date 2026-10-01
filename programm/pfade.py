"""
pfade.py  -  wo liegt was
=========================
Eine Stelle, an der alle Pfade bestimmt werden.  Wichtig, weil das Programm
auf zwei Arten laufen kann:

  * als Ordner        Latein/programm/*.py   +   Latein/daten/   +   Latein/lernstand/
  * als gepackte .exe  PyInstaller entpackt die mitgelieferten Daten in einen
                       Temp-Ordner, der beim Beenden geloescht wird.  Der
                       Lernstand darf deshalb NICHT dorthin, sondern muss
                       neben die .exe.

DATEN      nur lesen  (Vokabeldatei, Buchseiten)
LERNSTAND  wird beschrieben (Fehlerliste, Statistik) - ueberlebt das Programm
"""

import os
import sys
from pathlib import Path

ALS_EXE = getattr(sys, "frozen", False)

if ALS_EXE:
    # Von PyInstaller entpackte Daten liegen in _MEIPASS, der Lernstand
    # gehoert daneben in den Ordner der .exe.
    MITGELIEFERT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    BASIS = Path(sys.executable).resolve().parent
else:
    PROGRAMM = Path(__file__).resolve().parent
    BASIS = PROGRAMM.parent
    MITGELIEFERT = BASIS

# Die Handy-App setzt beide selbst: Android erlaubt Schreiben nur im
# App-eigenen Datenordner.
DATEN = Path(os.environ.get("LATEIN_DATEN") or MITGELIEFERT / "daten")
LERNSTAND = Path(os.environ.get("LATEIN_LERNSTAND") or BASIS / "lernstand")

VOKABELDATEI = DATEN / "vokabel_base.json"
GRAMMATIK_BILDER = DATEN / "grammatik_bilder"
FEHLERLISTE = LERNSTAND / "fehler_liste.json"
STATISTIK = LERNSTAND / "statistik.json"


def lernstand_bereitstellen():
    """Legt den Ordner für die Lernstände an, falls er noch fehlt."""
    try:
        LERNSTAND.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass          # z. B. schreibgeschützter Ort - das Programm läuft trotzdem
    return LERNSTAND
