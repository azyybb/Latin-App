"""
apk_bauen.py  -  baut Latein_Vokabeltrainer.apk fuer Android-Handys
==================================================================
Aufruf:   py -3 programm/apk_bauen.py     (oder Apk_bauen.bat doppelklicken)

Die App zeigt handy_server.py in einem eingebauten Browserfenster; die
Logik ist dieselbe wie am PC.  Gebaut wird mit BeeWare Briefcase.

Das Bauen braucht mehrere GB (Java, Android-SDK, Gradle).  Weil auf C: kaum
Platz ist, liegt alles davon in BAU (Standard D:\\LateinApp).  Der erste Lauf
laedt diese Werkzeuge herunter und dauert entsprechend; danach geht es schnell.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PROGRAMM = Path(__file__).resolve().parent
BASIS = PROGRAMM.parent
BAU = Path(os.environ.get("LATEIN_APK_BAU", r"D:\LateinApp"))
PROJEKT = BAU / "projekt"
PAKET = PROJEKT / "src" / "latein_vokabeln"
VENV = BAU / "venv"
BRIEFCASE = VENV / "Scripts" / "briefcase.exe"
NAME = "Latein_Vokabeltrainer.apk"
MINDESTENS_GB = 6

PROGRAMMDATEIEN = ["pfade.py", "bettervokable_search.py", "vokabel_search.py",
                   "fehler_datenbank.py", "grammatik.py", "handy_server.py",
                   "handy_oberflaeche.html"]


def umgebung():
    """Alle Werkzeug-Caches nach BAU - sonst landen GB davon auf C:."""
    env = dict(os.environ)
    for variable, ordner in (("BRIEFCASE_HOME", "briefcase-home"), ("GRADLE_USER_HOME", "gradle"),
                             ("ANDROID_USER_HOME", "android-user"), ("TEMP", "tmp"),
                             ("TMP", "tmp"), ("PIP_CACHE_DIR", "pip-cache")):
        pfad = BAU / ordner
        pfad.mkdir(parents=True, exist_ok=True)
        env[variable] = str(pfad)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def briefcase_bereitstellen(env):
    if BRIEFCASE.is_file():
        return True
    print("Richte Briefcase ein (einmalig) …")
    if subprocess.run([sys.executable, "-m", "venv", str(VENV)]).returncode:
        return False
    pip = [str(VENV / "Scripts" / "python.exe"), "-m", "pip", "install", "--quiet"]
    return subprocess.run(pip + ["briefcase"], env=env).returncode == 0


def projekt_fuellen():
    """App-Huelle, Programmteile und Daten ins Briefcase-Projekt kopieren."""
    PAKET.mkdir(parents=True, exist_ok=True)
    vorlage = PROGRAMM / "handy_app"
    shutil.copy2(vorlage / "pyproject.toml", PROJEKT / "pyproject.toml")
    shutil.copy2(vorlage / "app.py", PAKET / "app.py")
    (PAKET / "__init__.py").write_text("", encoding="utf-8")
    (PAKET / "__main__.py").write_text(
        "from latein_vokabeln.app import main\n\n"
        "if __name__ == \"__main__\":\n    main().main_loop()\n", encoding="utf-8")
    for name in PROGRAMMDATEIEN:
        shutil.copy2(PROGRAMM / name, PAKET / name)
    ziel = PAKET / "daten"
    shutil.rmtree(ziel, ignore_errors=True)
    ziel.mkdir()
    shutil.copy2(BASIS / "daten" / "vokabel_base.json", ziel / "vokabel_base.json")
    shutil.copytree(BASIS / "daten" / "grammatik_bilder", ziel / "grammatik_bilder")


def manifest_anpassen():
    """Die App spricht ihren eigenen Server ueber http://127.0.0.1 an.  Android
    sperrt unverschluesseltes HTTP seit Version 9 - auch zum eigenen Geraet."""
    treffer = list((PROJEKT / "build").rglob("src/main/AndroidManifest.xml"))
    if not treffer:
        print("AndroidManifest.xml nicht gefunden.")
        return False
    for datei in treffer:
        text = datei.read_text(encoding="utf-8")
        neu = text
        if "usesCleartextTraffic" not in neu:
            neu = re.sub(r"<application\b", '<application android:usesCleartextTraffic="true"',
                         neu, count=1)
        if "android.permission.INTERNET" not in neu:
            neu = neu.replace(
                "<application",
                '<uses-permission android:name="android.permission.INTERNET" />\n    '
                "<application", 1)
        if neu != text:
            datei.write_text(neu, encoding="utf-8")
    return True


MARKE = "/* latein: Tastatur 2 */"


def tastatur_anpassen():
    """Die Briefcase-Huelle zeichnet bis an den Bildschirmrand ("edge to edge").
    Dann verkleinert Android das Fenster bei offener Tastatur nicht mehr selbst,
    und die Huelle rueckt den Inhalt nur um Status- und Navigationsleiste ein.
    Die Tastatur liegt so UEBER der Seite; neuere Android-WebViews rechnen sie
    dann selbst heraus und rollen das Eingabefeld bei jedem Tastendruck nach
    oben - die Frage verschwindet.  Darum die Tastatur beim Einruecken
    mitzaehlen und die Masse danach verbrauchen, damit das Browserfenster sie
    nicht ein zweites Mal abzieht."""
    for datei in (PROJEKT / "build").rglob("src/main/AndroidManifest.xml"):
        text = datei.read_text(encoding="utf-8")
        if "windowSoftInputMode" not in text:
            # Unter Android 11 kommen die Tastaturmasse nur mit adjustResize an
            text = text.replace('android:name="org.beeware.android.MainActivity"',
                                'android:name="org.beeware.android.MainActivity"\n'
                                '            android:windowSoftInputMode="adjustResize"', 1)
            datei.write_text(text, encoding="utf-8")

    treffer = list((PROJEKT / "build").rglob("org/beeware/android/MainActivity.java"))
    if not treffer:
        print("MainActivity.java nicht gefunden.")
        return False
    for datei in treffer:
        text = datei.read_text(encoding="utf-8")
        if MARKE in text:
            continue
        alt = "systemBars.left, systemBars.top, systemBars.right, systemBars.bottom\n                );"
        rueckgabe = "                return insets;\n            }\n        );"
        if alt not in text or rueckgabe not in text:
            print("MainActivity.java sieht anders aus als erwartet - Tastatur-Anpassung fehlt.")
            return False
        neu = ("systemBars.left, systemBars.top, systemBars.right,\n"
               f"                    {MARKE} Math.max(systemBars.bottom,\n"
               "                        insets.getInsets(WindowInsetsCompat.Type.ime()).bottom)\n"
               "                );\n"
               "                v.requestLayout();")
        text = text.replace(alt, neu, 1)
        text = text.replace(rueckgabe, "                return WindowInsetsCompat.CONSUMED;\n"
                                       "            }\n        );", 1)
        datei.write_text(text, encoding="utf-8")
    return True


def briefcase(env, befehl_name, *optionen, fragen=False):
    """fragen=True laesst Rueckfragen durch - beim ersten Mal will Google, dass
    die Lizenzen des Android-SDK bestaetigt werden."""
    befehl = ([str(BRIEFCASE), befehl_name, "android", *optionen]
              + ([] if fragen else ["--no-input"]))
    print("\n>", " ".join(befehl[1:]))
    return subprocess.run(befehl, cwd=str(PROJEKT), env=env).returncode == 0


def main():
    if not BAU.anchor or not Path(BAU.anchor).exists():
        print(f"Das Laufwerk fuer den Bau gibt es nicht: {BAU}")
        print("Anderen Ort waehlen mit:  set LATEIN_APK_BAU=E:\\LateinApp")
        return 1
    frei = shutil.disk_usage(BAU.anchor).free / 1024 ** 3
    if frei < MINDESTENS_GB:
        print(f"Auf {BAU.anchor} sind nur {frei:.1f} GB frei, gebraucht werden etwa "
              f"{MINDESTENS_GB} GB.")
        return 1

    env = umgebung()
    if not briefcase_bereitstellen(env):
        print("Briefcase konnte nicht installiert werden.")
        return 1
    projekt_fuellen()

    neu = not list((PROJEKT / "build").rglob("src/main/AndroidManifest.xml"))
    if neu:
        print("Der erste Bau laedt Java und das Android-SDK herunter "
              "(einige GB) - das dauert eine Weile.")
        print("Fragt es nach den Android-SDK-Lizenzen: lesen und mit y bestaetigen.")
        if not briefcase(env, "create", fragen=True):
            print("\n'briefcase create' ist fehlgeschlagen.")
            return 1
    if not manifest_anpassen() or not tastatur_anpassen():
        return 1
    if not briefcase(env, "build", "--update"):
        print("\nDas Bauen ist fehlgeschlagen.")
        return 1

    apks = sorted((PROJEKT / "build").rglob("outputs/apk/debug/*.apk"),
                  key=lambda p: p.stat().st_mtime)
    if not apks:
        print("\nDie APK wurde nicht gefunden.")
        return 1
    ziel = BASIS / NAME
    shutil.copy2(apks[-1], ziel)
    print(f"\nFertig:  {ziel.name}  ({ziel.stat().st_size / 1024 / 1024:.0f} MB)")
    print(f"Liegt in: {BASIS}")
    print("\nAufs Handy bringen: Datei per USB, Google Drive oder Mail aufs Handy,")
    print("dort antippen und 'Installation aus unbekannten Quellen' einmal erlauben.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
