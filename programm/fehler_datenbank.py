"""
fehler_datenbank.py  -  merkt sich falsch beantwortete Vokabeln
===============================================================
Gespeichert wird in fehler_liste.json neben den Programmdateien, damit die
Liste ein Programmende ueberlebt.

Punktekonto:
    * Eine falsch beantwortete Vokabel kommt mit 0 Punkten in die Liste.
    * richtig  ->  +1 Punkt
    * falsch   ->  -1 Punkt (nie unter 0)
    * bei ZIEL_PUNKTE Punkten gilt sie als geschafft und wandert ins Archiv.

Archivierte Vokabeln bleiben mit ihrer Bilanz gespeichert.  Wer spaeter wieder
darauf hereinfaellt, bekommt sie samt Vorgeschichte zurueck in die Liste.
"""

import json
import os
from datetime import datetime
from pathlib import Path

import pfade
from bettervokable_search import norm

DATEI = pfade.FEHLERLISTE
STATISTIK_DATEI = pfade.STATISTIK
ZIEL_PUNKTE = 3
VERSION = 1


def jetzt():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def schreiben(pfad, daten):
    """Erst in eine Nebendatei, dann umbenennen: ein Absturz mittendrin darf
    den bereits gespeicherten Stand nicht zerstoeren."""
    pfade.lernstand_bereitstellen()
    neben = pfad.with_name(pfad.name + ".tmp")
    try:
        pfad.parent.mkdir(parents=True, exist_ok=True)   # Website: Ordner je Nutzer
        with open(neben, "w", encoding="utf-8") as fh:
            json.dump(daten, fh, ensure_ascii=False, indent=1)
        os.replace(neben, pfad)
    except OSError:
        return False
    return True


def schluessel(gruppe, eintrag):
    """Stabiler Name einer Vokabel - unabhaengig von der Reihenfolge in der
    Datenbank, damit gespeicherte Eintraege spaeter wiedergefunden werden.
    Verben laufen ueber den Infinitiv, sonst ueber das Lemma."""
    if gruppe["wortart"] == "Verb" and gruppe.get("inf"):
        kern = norm(gruppe["inf"])
    else:
        kern = norm(eintrag["latein"])
    return f"{gruppe['wortart']}|{kern}"


class FehlerListe:
    """Laedt, pflegt und speichert die Fehlervokabeln."""

    def __init__(self, pfad=DATEI):
        self.pfad = Path(pfad)
        self.vokabeln = {}
        self.warnung = None
        self.laden()

    # ------------------------------------------------------------ Datei
    def laden(self):
        try:
            with open(self.pfad, encoding="utf-8") as fh:
                daten = json.load(fh)
        except FileNotFoundError:
            return
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as ex:
            # Eine kaputte Datei wird beiseitegelegt statt ueberschrieben -
            # vielleicht laesst sich daraus noch etwas retten.
            self.warnung = f"Die Fehlerliste war beschädigt ({ex}).  Sie liegt jetzt neben dem Programm als fehler_liste.defekt.json."
            try:
                self.pfad.replace(self.pfad.with_name("fehler_liste.defekt.json"))
            except OSError:
                pass
            return
        if not isinstance(daten, dict):
            return
        roh = daten.get("vokabeln")
        if not isinstance(roh, dict):
            return
        for k, v in roh.items():
            if isinstance(v, dict) and v.get("latein"):
                v.setdefault("punkte", 0)
                v.setdefault("falsch", 1)
                v.setdefault("richtig", 0)
                v.setdefault("archiviert", False)
                self.vokabeln[k] = v

    def speichern(self):
        daten = {"version": VERSION, "geaendert": jetzt(), "vokabeln": self.vokabeln}
        if not schreiben(self.pfad, daten):
            self.warnung = "Die Fehlerliste konnte nicht gespeichert werden."
            return False
        return True

    # ------------------------------------------------------------ Pflege
    def _neu(self, gruppe, eintrag):
        return {
            "latein": eintrag["latein"],
            "deutsch": eintrag["deutsch"],
            "lektion": eintrag["lektion"],
            "wortart": gruppe["wortart"],
            "punkte": 0,
            "falsch": 0,
            "richtig": 0,
            "seit": jetzt(),
            "zuletzt": jetzt(),
            "archiviert": False,
            "geschafft_am": None,
        }

    def falsch(self, gruppe, eintrag):
        """Vokabel eintragen bzw. einen Punkt abziehen.  Gibt den Eintrag zurück."""
        k = schluessel(gruppe, eintrag)
        v = self.vokabeln.get(k)
        if v is None:
            v = self.vokabeln[k] = self._neu(gruppe, eintrag)
        elif v["archiviert"]:
            # Rueckfall: zurueck in die Übung, die Bilanz bleibt erhalten.
            v["archiviert"] = False
            v["geschafft_am"] = None
            v["punkte"] = 0
        else:
            v["punkte"] = max(0, v["punkte"] - 1)
        v["falsch"] += 1
        v["zuletzt"] = jetzt()
        # Bedeutung und Lektion mitziehen, falls die Vokabeldatei sich ändert
        v["latein"], v["deutsch"] = eintrag["latein"], eintrag["deutsch"]
        v["lektion"], v["wortart"] = eintrag["lektion"], gruppe["wortart"]
        self.speichern()
        return v

    def richtig(self, gruppe, eintrag):
        """Punkt gutschreiben, falls die Vokabel in der Übung ist.
        Gibt (Eintrag, geschafft) zurück; (None, False) wenn sie nicht drin ist."""
        k = schluessel(gruppe, eintrag)
        v = self.vokabeln.get(k)
        if v is None or v["archiviert"]:
            return None, False
        v["punkte"] += 1
        v["richtig"] += 1
        v["zuletzt"] = jetzt()
        geschafft = v["punkte"] >= ZIEL_PUNKTE
        if geschafft:
            v["archiviert"] = True
            v["geschafft_am"] = jetzt()
        self.speichern()
        return v, geschafft

    def zuruecksetzen(self, k):
        v = self.vokabeln.get(k)
        if not v:
            return
        v["punkte"] = 0
        v["archiviert"] = False
        v["geschafft_am"] = None
        v["zuletzt"] = jetzt()
        self.speichern()

    def entfernen(self, k):
        if self.vokabeln.pop(k, None) is not None:
            self.speichern()

    def alles_loeschen(self):
        self.vokabeln.clear()
        self.speichern()

    # ------------------------------------------------------------ Abfragen
    def aktive(self):
        """Zu übende Vokabeln, die schwächsten zuerst."""
        offen = [(k, v) for k, v in self.vokabeln.items() if not v["archiviert"]]
        return sorted(offen, key=lambda kv: (kv[1]["punkte"], -kv[1]["falsch"],
                                             kv[1]["lektion"], kv[1]["latein"]))

    def archiv(self):
        fertig = [(k, v) for k, v in self.vokabeln.items() if v["archiviert"]]
        return sorted(fertig, key=lambda kv: kv[1].get("geschafft_am") or "", reverse=True)

    def zahlen(self):
        aktiv = self.aktive()
        return {"offen": len(aktiv), "geschafft": len(self.archiv()),
                "falsch_gesamt": sum(v["falsch"] for v in self.vokabeln.values())}

    def paare(self, db):
        """Die offenen Vokabeln als (gruppe, eintrag) - Paare für das Quiz.
        Einträge, die es in der Vokabeldatei nicht mehr gibt, fallen weg."""
        index = {}
        for g in db.groups:
            for e in g["entries"]:
                index.setdefault(schluessel(g, e), (g, e))
        ergebnis = []
        for k, _v in self.aktive():
            if k in index:
                ergebnis.append(index[k])
        return ergebnis

    def fortschritt(self, v):
        """●●○ als kleine Fortschrittsanzeige."""
        voll = max(0, min(ZIEL_PUNKTE, v["punkte"]))
        return "●" * voll + "○" * (ZIEL_PUNKTE - voll)


class Statistik:
    """Zaehlt dauerhaft mit, wie viel geuebt wurde.

    Gespeichert wird in statistik.json:
      * abfragen  - wie viele Fragen insgesamt beantwortet wurden
      * perfekt / richtig / falsch - wie sie ausgegangen sind
      * vokabeln  - je Vokabel dieselben Zaehler; die Anzahl der Eintraege ist
                    die Zahl der EINZELNEN Vokabeln, die schon drankamen
    """

    FELDER = ("abfragen", "perfekt", "richtig", "falsch")

    def __init__(self, pfad=STATISTIK_DATEI):
        self.pfad = Path(pfad)
        self.gesamt = {f: 0 for f in self.FELDER}
        self.vokabeln = {}
        self.seit = None
        self.warnung = None
        self.laden()

    # ------------------------------------------------------------ Datei
    def laden(self):
        try:
            with open(self.pfad, encoding="utf-8") as fh:
                daten = json.load(fh)
        except FileNotFoundError:
            self.seit = jetzt()
            return
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as ex:
            self.warnung = f"Die Statistik war beschädigt ({ex}) und beginnt von vorn."
            self.seit = jetzt()
            return
        if not isinstance(daten, dict):
            self.seit = jetzt()
            return
        for f in self.FELDER:
            wert = daten.get("gesamt", {}).get(f, 0)
            self.gesamt[f] = wert if isinstance(wert, int) and wert >= 0 else 0
        roh = daten.get("vokabeln")
        if isinstance(roh, dict):
            for k, v in roh.items():
                if isinstance(v, dict):
                    self.vokabeln[k] = {f: int(v.get(f, 0) or 0) for f in self.FELDER}
        self.seit = daten.get("seit") or jetzt()

    def speichern(self):
        daten = {"version": VERSION, "seit": self.seit, "geaendert": jetzt(),
                 "gesamt": self.gesamt, "vokabeln": self.vokabeln}
        if not schreiben(self.pfad, daten):
            self.warnung = "Die Statistik konnte nicht gespeichert werden."
            return False
        return True

    # ------------------------------------------------------------ Zaehlen
    def buchen(self, gruppe, eintrag, bewertung, speichern=True):
        """bewertung: "perfekt", "richtig" oder "falsch"."""
        if bewertung not in ("perfekt", "richtig", "falsch"):
            return
        k = schluessel(gruppe, eintrag)
        eigen = self.vokabeln.setdefault(k, {f: 0 for f in self.FELDER})
        for ziel in (self.gesamt, eigen):
            ziel["abfragen"] += 1
            ziel[bewertung] += 1
        if speichern:
            self.speichern()

    def zuruecksetzen(self):
        self.gesamt = {f: 0 for f in self.FELDER}
        self.vokabeln.clear()
        self.seit = jetzt()
        self.speichern()

    # ------------------------------------------------------------ Abfragen
    def zahlen(self):
        z = dict(self.gesamt)
        z["einzelne"] = len(self.vokabeln)
        z["gekonnt"] = sum(1 for v in self.vokabeln.values()
                           if v["perfekt"] + v["richtig"] > 0)
        return z

    def kurzfassung(self):
        z = self.zahlen()
        return (f"gelernt: {z['einzelne']} einzelne Vokabeln  ·  "
                f"{z['abfragen']} Abfragen")
