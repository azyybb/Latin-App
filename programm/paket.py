"""
paket.py  -  packt den Vokabeltrainer als ZIP zum Verschicken
=============================================================
Aufruf:   py -3 programm/paket.py      (oder Paket_erstellen.bat doppelklicken)

Im ZIP liegt die Ordner-Fassung: die braucht Python, ist dafuer klein.
Wer kein Python installieren mag, bekommt stattdessen einfach die Datei
Latein_Vokabeltrainer.exe geschickt - die laeuft allein.

Die eigenen Lernstaende bleiben draussen; der Empfaenger faengt bei null an.
"""

import sys
import zipfile
from pathlib import Path

PROGRAMM = Path(__file__).resolve().parent
BASIS = PROGRAMM.parent
NAME = "Latein_Vokabeltrainer.zip"

PROGRAMMDATEIEN = ["pfade.py", "bettervokable_search.py", "vokabel_search.py",
                   "fehler_datenbank.py", "grammatik.py", "vokabel_gui.py"]
WURZEL = ["Latein.bat"]

LIESMICH = """Lateinischer Vokabeltrainer
===========================

Zwei Wege, das Programm zu starten - such dir einen aus.

A)  Ohne Installation
    Falls du zusaetzlich die Datei  Latein_Vokabeltrainer.exe  bekommen hast:
    einfach doppelklicken.  Mehr ist nicht noetig.
    Beim ersten Start meldet sich Windows eventuell mit
    "Windows hat Ihren PC geschuetzt" - dort auf "Weitere Informationen"
    und dann "Trotzdem ausfuehren" klicken.  Das kommt nur einmal.

B)  Mit Python  (dieser Ordner)
    1. Den Ordner irgendwohin entpacken, z. B. auf den Desktop.
    2. Auf  Latein.bat  doppelklicken.

    Fehlt Python, sagt die Datei das und erklaert es:
    1. https://www.python.org/downloads/  oeffnen
    2. Python herunterladen und installieren
    3. Im Installationsfenster UNBEDINGT beide Haken setzen:
          [x] Add python.exe to PATH
          [x] py launcher
    4. Danach wieder Latein.bat doppelklicken.

    Die Buchseiten im Reiter "Grammatik" brauchen zusaetzlich:
          py -3 -m pip install pillow
    Alles andere laeuft auch ohne.


Was drin ist
------------
  Suche           Lateinische Woerter auch in gebeugter Form nachschlagen
                  (rogaverunt, altissimum, castra posuerunt) oder deutsch suchen.
  Quiz            Latein->Deutsch, Deutsch->Latein, gemischt oder Formen-Quiz -
                  beim Formen-Quiz einstellbar, welche Grammatik drankommt.
  Fehlervokabeln  Was du falsch hattest, wird gesammelt und gezielt geuebt.
  Grammatik       Formentabellen je Lektion, dazu die Buchseiten als Foto.
  Alle Vokabeln   Die ganze Wortliste, sortier- und durchsuchbar.


Ordner
------
  programm\\    der Programmcode
  daten\\       Vokabeldatei und Buchseiten
  lernstand\\   deine Fehlerliste und Statistik (wird selbst angelegt)

Wenn etwas nicht gefunden wird:  Latein_Vokabeltrainer.exe --pfade
schreibt eine Datei lernstand\\pfade.txt mit allen Suchorten.
"""


def zielordner():
    """Lieber auf den Desktop - dort findet man die Datei zum Verschicken."""
    desktop = Path.home() / "Desktop"
    return desktop if desktop.is_dir() else BASIS


def main():
    fehlend = [n for n in PROGRAMMDATEIEN if not (PROGRAMM / n).is_file()]
    fehlend += [n for n in WURZEL if not (BASIS / n).is_file()]
    if not (BASIS / "daten" / "vokabel_base.json").is_file():
        fehlend.append("daten/vokabel_base.json")
    if fehlend:
        print("Diese Dateien fehlen und koennen nicht gepackt werden:")
        for d in fehlend:
            print("   ", d)
        return 1

    ziel = zielordner() / NAME
    with zipfile.ZipFile(ziel, "w", zipfile.ZIP_DEFLATED) as zip_datei:
        for name in WURZEL:
            zip_datei.write(BASIS / name, f"Latein/{name}")
        for name in PROGRAMMDATEIEN:
            zip_datei.write(PROGRAMM / name, f"Latein/programm/{name}")
        daten = BASIS / "daten"
        for datei in sorted(daten.rglob("*")):
            if datei.is_file():
                zip_datei.write(datei, f"Latein/{datei.relative_to(BASIS).as_posix()}")
        zip_datei.writestr("Latein/LIESMICH.txt", LIESMICH)

    with zipfile.ZipFile(ziel) as z:
        anzahl = len(z.namelist())
    print(f"{ziel.name}  -  {anzahl} Dateien, "
          f"{ziel.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"Liegt in: {ziel.parent}")

    exe = BASIS / "Latein_Vokabeltrainer.exe"
    print()
    if exe.is_file():
        print(f"Wer kein Python installieren mag, bekommt stattdessen die Datei")
        print(f"   {exe}")
        print(f"   ({exe.stat().st_size / 1024 / 1024:.0f} MB) - die laeuft allein.")
    else:
        print("Eine .exe gibt es noch nicht.  Bauen mit:  Exe_bauen.bat")
    return 0


if __name__ == "__main__":
    sys.exit(main())
