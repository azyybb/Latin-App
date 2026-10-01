"""
exe_bauen.py  -  baut Latein_Vokabeltrainer.exe
===============================================
Aufruf:   py -3 programm/exe_bauen.py     (oder Exe_bauen.bat doppelklicken)

Die .exe enthaelt Python, tkinter, Pillow, die Vokabeldatei und die
Buchseiten - der Empfaenger braucht nichts zu installieren.

Der Lernstand wandert NICHT in die .exe: PyInstaller entpackt den Inhalt bei
jedem Start in einen Temp-Ordner, der danach geloescht wird.  pfade.py legt
fehler_liste.json und statistik.json deshalb in einen Ordner "lernstand"
neben der .exe.
"""

import shutil
import subprocess
import sys
from pathlib import Path

PROGRAMM = Path(__file__).resolve().parent
BASIS = PROGRAMM.parent
NAME = "Latein_Vokabeltrainer"


def main():
    try:
        import PyInstaller                      # noqa: F401
    except ImportError:
        print("PyInstaller fehlt.  Installieren mit:")
        print("   py -3 -m pip install pyinstaller")
        return 1

    daten = BASIS / "daten"
    if not (daten / "vokabel_base.json").is_file():
        print(f"Die Vokabeldatei fehlt: {daten / 'vokabel_base.json'}")
        return 1

    arbeit = BASIS / "bauen"
    befehl = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onefile",                 # eine einzige Datei
        "--windowed",                # kein Konsolenfenster
        "--name", NAME,
        "--paths", str(PROGRAMM),
        # Das Programm braucht nur tkinter und Pillow.  Ohne diese Ausschlüsse
        # packt PyInstaller alles mit ein, was zufällig installiert ist
        # (numpy und matplotlib allein machen rund 60 MB aus).
        *[arg for modul in ("numpy", "matplotlib", "scipy", "pandas", "IPython",
                            "PyQt5", "PyQt6", "PySide2", "PySide6", "setuptools",
                            "pytest", "sqlite3", "pydoc", "unittest", "email",
                            "http", "xml", "pip")
          for arg in ("--exclude-module", modul)],
        # Die Daten liegen in der .exe unter "daten" - genau dort sucht pfade.py
        "--add-data", f"{daten}{';' if sys.platform == 'win32' else ':'}daten",
        "--distpath", str(BASIS),
        "--workpath", str(arbeit / "arbeit"),
        "--specpath", str(arbeit),
        str(PROGRAMM / "vokabel_gui.py"),
    ]

    print("Das Bauen dauert ein bis zwei Minuten …\n")
    ergebnis = subprocess.run(befehl, cwd=str(BASIS))
    if ergebnis.returncode != 0:
        print("\nDas Bauen ist fehlgeschlagen.")
        return ergebnis.returncode

    shutil.rmtree(arbeit, ignore_errors=True)
    exe = BASIS / f"{NAME}.exe"
    if not exe.is_file():
        print("\nDie .exe wurde nicht gefunden.")
        return 1
    print(f"\nFertig:  {exe.name}  ({exe.stat().st_size / 1024 / 1024:.0f} MB)")
    print(f"Liegt in: {BASIS}")
    print("\nBeim ersten Start kann Windows eine Warnung zeigen "
          "(„Windows hat Ihren PC geschuetzt“).")
    print("Dort auf „Weitere Informationen“ und dann "
          "„Trotzdem ausfuehren“ klicken.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
