"""
Hülle der Handy-App: startet handy_server.py und zeigt ihn in einem
eingebauten Browserfenster.  Alles andere ist derselbe Code wie am PC.
"""

import os
import sys
from pathlib import Path

import toga
from toga.style import Pack

HIER = Path(__file__).resolve().parent


class LateinVokabeln(toga.App):
    def startup(self):
        # Android erlaubt Schreiben nur im App-eigenen Datenordner; pfade.py
        # liest beide Orte aus der Umgebung, darum vor dem ersten Import setzen.
        lernstand = Path(self.paths.data) / "lernstand"
        lernstand.mkdir(parents=True, exist_ok=True)
        os.environ["LATEIN_DATEN"] = str(HIER / "daten")
        os.environ["LATEIN_LERNSTAND"] = str(lernstand)
        # Die Programmteile importieren sich gegenseitig ohne Paketnamen
        sys.path.insert(0, str(HIER))
        import handy_server

        adresse = handy_server.starten()
        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_window.content = toga.WebView(url=adresse, style=Pack(flex=1))
        self.main_window.show()


def main():
    return LateinVokabeln()
