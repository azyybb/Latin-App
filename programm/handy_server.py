"""
handy_server.py  -  Oberflaeche fuer das Handy
==============================================
Ein kleiner Webserver um dieselbe Logik wie im PC-Fenster.  Die Handy-App
zeigt ihn in einem eingebauten Browserfenster.  Am PC laesst er sich zum
Ausprobieren direkt starten:

    py -3 handy_server.py          ->  http://127.0.0.1:8765

Der Quizablauf entspricht QuizReiter in vokabel_gui.py - wer dort die
Bewertung aendert, muss es hier auch tun.
"""

import json
import random
import re
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import fehler_datenbank as FD
import grammatik as GR
import pfade
import vokabel_search as quiz
from bettervokable_search import CONJ_NAMES, FORMEN_LABEL, WORTART_ORDER, VokabelBase, norm

OBERFLAECHE = Path(__file__).with_name("handy_oberflaeche.html")
SPALTEN_NAMEN = {"lektion": "Lektion", "latein": "Vokabel", "wortart": "Wortart",
                 "deutsch": "Bedeutung", "formen": "Formen"}


# Grammatik im Formen-Quiz: standardmaessig angehakt.  Partizipien,
# Konjunktiv usw. sind oft noch zu schwer - die lassen sich per Haken
# dazunehmen.
GRAMMATIK_STANDARD = ("Präsens", "Imperfekt", "Perfekt", "Plusquamperfekt", "Futur",
                      "Passiv", "Imperativ und Infinitiv",
                      "Deklination (Substantive, Adjektive)")
GRAMMATIK_WAHL = [n for n, anfaenge in quiz.FORM_BEREICHE if anfaenge]


def bereich_lesen(d):
    """Angehakte Grammatik -> Tupel von Formanfaengen (None = alles).
    Das alte Einzelfeld "bereich" geht weiterhin."""
    namen = d.get("bereiche")
    if isinstance(namen, list):
        tabelle = dict(quiz.FORM_BEREICHE)
        anfaenge = []
        for n in namen:
            for a in tabelle.get(n) or ():
                if a not in anfaenge:
                    anfaenge.append(a)
        return tuple(anfaenge)
    return dict(quiz.FORM_BEREICHE).get(d.get("bereich"))


def anzahl_lesen(wunsch, vorhanden):
    wunsch = str(wunsch).strip().lower()
    if wunsch in ("alle", "all", "*", ""):
        return vorhanden
    try:
        return max(1, min(2000, int(wunsch)))
    except ValueError:
        return min(10, vorhanden)


def auswahl_lesen(t, d):
    """Quiz-Einstellungen -> {"paare", "modus", "formen", "anzahl"}
    oder {"fehler": ...}.  Benutzt vom Quiz und von der Arena."""
    lektionen = quiz.lektionen_parsen(str(d.get("lektionen", "alle")), t.lektionen)
    if not lektionen:
        return {"fehler": f"Keine gültige Lektionsangabe. Es gibt die Lektionen "
                          f"{t.lektionen[0]}–{t.lektionen[-1]}. "
                          f"Beispiele: 1-8 · 3,5 · alle"}
    wortart = d.get("wortart", "alle")
    wortarten = None if wortart == "alle" else {wortart}
    modus = d.get("modus", "ld")
    if modus not in ("ld", "dl", "mix", "formen"):
        modus = "ld"

    bis = str(d.get("bis", "passend"))
    if bis == "alle":
        bis_lektion = None
    elif bis.isdigit():
        bis_lektion = int(bis)
    else:
        bis_lektion = max(lektionen)
    bereich = bereich_lesen(d)
    art = d.get("art", "gemischt")

    paare = quiz.gruppen_waehlen(t.db, lektionen, wortarten)
    if modus == "formen":
        if bereich == ():
            return {"fehler": "Bitte mindestens eine Grammatik ankreuzen."}
        paare = [(g, e) for g, e in paare if quiz.formen_zeilen(g, bis_lektion, bereich)]
    if not paare:
        return {"fehler": "Zu dieser Auswahl gibt es keine Vokabeln. Bitte anders wählen."}
    return {"paare": paare, "modus": modus, "formen": (bis_lektion, bereich, art),
            "anzahl": anzahl_lesen(d.get("anzahl", "10"), len(paare))}


def aufgaben_ziehen(paare, anzahl):
    return (random.sample(paare, anzahl) if anzahl <= len(paare)
            else random.choices(paare, k=anzahl))


def aufgabe_bauen(db, gruppe, eintrag, modus, formen):
    """Eine Frage samt Pruefer - None, wenn die Vokabel keine passende Form hat."""
    if modus == "formen":
        bis_lektion, bereich, art = formen
        zeilen = quiz.formen_zeilen(gruppe, bis_lektion, bereich)
        if not zeilen:
            return None
        label, person, alts = random.choice(zeilen)
        bestimmung = label + (", " + person if person else "")
        bilden = art == "bilden" or (art == "gemischt" and random.random() < 0.5)
        if bilden:
            erlaubt = {norm(a) for a in alts if norm(a)}

            def pruefe_form(antwort, erlaubt=erlaubt):
                ok, _t, exakt = quiz._passt(norm(antwort), erlaubt)
                return (quiz.PERFEKT if exakt else
                        quiz.RICHTIG if ok else quiz.FALSCH), None

            return {"frage": gruppe["lemma"],
                    "untertitel": f"Bilde die Form:  {bestimmung}",
                    "zusatz": eintrag["deutsch"],
                    "loesung": " / ".join(alts),
                    "pruefer": pruefe_form}
        return {"frage": alts[0],
                "untertitel": "Von welcher Vokabel stammt diese Form?",
                "zusatz": "",
                "loesung": f"{gruppe['lemma']}   ({bestimmung})   –   {eintrag['deutsch']}",
                "pruefer": lambda a: (quiz.pruefe_latein(a, gruppe, db)[0], None)}

    richtung = 1 if modus == "ld" else 2 if modus == "dl" else random.choice((1, 2))
    kopf = f"Lektion {eintrag['lektion']}  ·  {gruppe['wortart']}"
    if richtung == 1:
        return {"frage": eintrag["latein"],
                "untertitel": f"{kopf}  ·  ins Deutsche",
                "zusatz": "",
                "loesung": eintrag["deutsch"],
                "pruefer": lambda a: (quiz.pruefe_deutsch(a, eintrag, db, gruppe)[0], None)}

    def pruefe(antwort):
        bewertung, _treffer, form = quiz.pruefe_latein(antwort, gruppe, db)
        hinweis = (f"Das ist {form} – die Grundform heißt {eintrag['latein']}."
                   if form else None)
        return bewertung, hinweis

    return {"frage": eintrag["deutsch"],
            "untertitel": f"{kopf}  ·  ins Lateinische",
            "zusatz": "",
            "loesung": eintrag["latein"],
            "pruefer": pruefe}


def antwort_bewerten(t, gruppe, eintrag, frage, antwort):
    """Prueft, bucht Statistik und Fehlerliste und liefert die Rueckmeldung."""
    bewertung, hinweis = frage["pruefer"](antwort)
    t.statistik.buchen(gruppe, eintrag, bewertung)
    merker = ""
    if bewertung == quiz.FALSCH:
        v = t.fehler.falsch(gruppe, eintrag)
        merker = (f"Kommt in die Fehlerliste: {t.fehler.fortschritt(v)}  "
                  f"({v['falsch']}× falsch)")
    else:
        v, geschafft = t.fehler.richtig(gruppe, eintrag)
        if geschafft:
            merker = "Geschafft – diese Vokabel ist jetzt aus der Fehlerliste raus."
        elif v:
            merker = (f"Fehlerliste: {t.fehler.fortschritt(v)}  "
                      f"noch {FD.ZIEL_PUNKTE - v['punkte']}× richtig")
    return {"bewertung": bewertung, "antwort": antwort, "loesung": frage["loesung"],
            "formen": quiz.stammformen(gruppe, eintrag), "hinweis": hinweis or "",
            "merker": merker, "nachschlagen": eintrag["latein"]}


class Quiz:
    """Einstellungen -> Frage -> Antwort -> ... -> Ergebnis."""

    def __init__(self, trainer):
        self.t = trainer
        self.phase = None
        self.aufgaben = []
        self.nummer = self.punkte = 0
        self.zaehler = {}
        self.fehler_eintraege = []
        self.rueckmeldung = {}

    # -------------------------------------------------- Start
    def starten(self, d):
        a = auswahl_lesen(self.t, d)
        if "fehler" in a:
            return a
        self._beginnen(a["paare"], a["modus"], a["formen"], a["anzahl"])
        return self.zustand()

    def fehlerliste_ueben(self, d):
        paare = self.t.fehler.paare(self.t.db)
        if not paare:
            return {"fehler": "In der Liste steht keine Vokabel, die es in der "
                              "Vokabeldatei noch gibt."}
        self._beginnen(paare, d.get("modus", "ld"), (None, None, "gemischt"), len(paare))
        return self.zustand()

    def _beginnen(self, paare, modus, formen, anzahl):
        self.aufgaben = aufgaben_ziehen(paare, anzahl)
        self.einstellung = (modus, formen)
        self.nummer, self.punkte = 0, 0
        self.zaehler = {quiz.PERFEKT: 0, quiz.RICHTIG: 0, quiz.FALSCH: 0}
        self.fehler_eintraege = []
        self._naechste()

    # -------------------------------------------------- Ablauf
    def _naechste(self):
        while self.nummer < len(self.aufgaben):
            gruppe, eintrag = self.aufgaben[self.nummer]
            modus, formen = self.einstellung
            self.frage = aufgabe_bauen(self.t.db, gruppe, eintrag, modus, formen)
            if self.frage is not None:
                self.rueckmeldung = {}
                self.phase = "frage"
                return
            self.aufgaben.pop(self.nummer)       # keine Formen -> ueberspringen
        self._ergebnis()

    def pruefen(self, d):
        if self.phase != "frage":
            return self.zustand()
        antwort = str(d.get("antwort", "")).strip()
        gruppe, eintrag = self.aufgaben[self.nummer]
        self.rueckmeldung = antwort_bewerten(self.t, gruppe, eintrag, self.frage, antwort)
        bewertung = self.rueckmeldung["bewertung"]
        self.zaehler[bewertung] += 1
        if bewertung == quiz.FALSCH:
            self.fehler_eintraege.append(eintrag)
        else:
            self.punkte += 1
        self.nummer += 1
        self.phase = "antwort"
        return self.zustand()

    def weiter(self, _d=None):
        if self.phase == "antwort":
            self._naechste()
        return self.zustand()

    def beenden(self, _d=None):
        if self.phase in ("frage", "antwort") and self.nummer:
            self._ergebnis()
        else:
            self.phase = None
        return self.zustand()

    def _ergebnis(self):
        self.phase = "ende"
        gestellt = self.nummer
        self.ergebnis = {"punkte": self.punkte, "gestellt": gestellt,
                         "prozent": round(100 * self.punkte / gestellt) if gestellt else 0,
                         "insgesamt": self.t.lernstand_text(),
                         "fehler": [{"latein": e["latein"], "deutsch": e["deutsch"]}
                                    for e in self.fehler_eintraege]}

    def zustand(self, _d=None):
        z = self.zaehler
        daten = {"phase": self.phase, "nummer": self.nummer, "gesamt": len(self.aufgaben),
                 "perfekt": z.get(quiz.PERFEKT, 0), "richtig": z.get(quiz.RICHTIG, 0),
                 "falsch": z.get(quiz.FALSCH, 0), "lernstand": self.t.lernstand_text()}
        if self.phase in ("frage", "antwort"):
            daten.update({k: self.frage[k] for k in ("frage", "untertitel", "zusatz")})
            daten.update(self.rueckmeldung)
        elif self.phase == "ende":
            daten.update(self.ergebnis)
        return daten


class Grundlage:
    """Was fuer alle gleich ist: Vokabeln und Grammatikthemen.  Das Laden
    dauert - die Website (web_server.py) teilt eine Grundlage unter allen
    Nutzern."""

    def __init__(self):
        self.db = VokabelBase()
        self.lektionen = sorted({e["lektion"] for e in self.db.entries})
        self.neu = GR.neu_je_lektion(self.db)
        self.themen = GR.themen(self.db)


class Trainer:
    """Haelt Vokabeln, Fehlerliste und Statistik - einmal fuer die ganze App.
    Mit `lernstand` (Ordner) bekommt jeder Website-Nutzer seinen eigenen."""

    def __init__(self, grundlage=None, lernstand=None):
        g = grundlage or Grundlage()
        self.db, self.lektionen, self.neu, self.themen = g.db, g.lektionen, g.neu, g.themen
        if lernstand is None:
            self.fehler = FD.FehlerListe()
            self.statistik = FD.Statistik()
        else:
            self.fehler = FD.FehlerListe(Path(lernstand) / pfade.FEHLERLISTE.name)
            self.statistik = FD.Statistik(Path(lernstand) / pfade.STATISTIK.name)
        self.quiz = Quiz(self)
        self.aktionen = {
            "start": self.start, "suche": self.suche, "formen": self.formen,
            "quiz/start": self.quiz.starten, "quiz/fehlerliste": self.quiz.fehlerliste_ueben,
            "quiz/pruefen": self.quiz.pruefen, "quiz/weiter": self.quiz.weiter,
            "quiz/beenden": self.quiz.beenden, "quiz/zustand": self.quiz.zustand,
            "fehler": self.fehlerliste, "fehler/zuruecksetzen": self.fehler_zuruecksetzen,
            "fehler/entfernen": self.fehler_entfernen,
            "grammatik": self.grammatik, "vokabeln": self.vokabeln,
        }

    # -------------------------------------------------- Allgemein
    def lernstand_text(self):
        s = self.statistik.zahlen()
        return (f"Bisher gelernt: {s['einzelne']} einzelne Vokabeln · {s['abfragen']} Abfragen "
                f"(★ {s['perfekt']} · ✓ {s['richtig']} · ✗ {s['falsch']})")

    def fuss(self):
        zahlen = self.fehler.zahlen()
        s = self.statistik.zahlen()
        return (f"{len(self.db.entries)} Vokabeln · {len(self.db.form_index)} erkannte Formen · "
                f"{zahlen['offen']} in Übung · gelernt: {s['einzelne']} einzelne / "
                f"{s['abfragen']} Abfragen")

    def start(self, _d):
        arten = ["alle"] + [w for w in WORTART_ORDER
                            if any(g["wortart"] == w for g in self.db.groups)]
        return {"lektionen": self.lektionen, "wortarten": arten,
                "bereiche": [n for n, _p in quiz.FORM_BEREICHE],
                "grammatik": GRAMMATIK_WAHL, "grammatik_standard": list(GRAMMATIK_STANDARD),
                "arten": [list(a) for a in quiz.ARTEN],
                "themen": [n for n, _s in self.themen],
                "ziel": FD.ZIEL_PUNKTE, "fuss": self.fuss(),
                "lernstand": self.lernstand_text(),
                "warnungen": [w for w in (self.fehler.warnung, self.statistik.warnung) if w],
                "quiz": self.quiz.zustand()}

    # -------------------------------------------------- Suche
    def _gruppe_stuecke(self, gid, info=None, deutsch_treffer=False, einzug=""):
        g = self.db.groups[gid]
        kopf = f"{einzug}{g['lemma']}   ({g['wortart']}"
        if g["wortart"] == "Verb" and g.get("conj"):
            kopf += f", {CONJ_NAMES[g['conj']]}"
        stuecke = [{"t": kopf + ")", "k": "titel", "g": gid if g.get("par") else None}]

        def dazu(text, art):
            stuecke.append({"t": text, "k": art})

        if info:
            if info.get("enclitic"):
                dazu(f"{einzug}   Angehängtes {info['enclitic']} erkannt", "leise")
            if info["labels"]:
                sauber, notizen = [], []
                for label in info["labels"][:6]:
                    sauber.append(quiz.sauberes_label(label))
                    for notiz in re.findall(r"\[([^\]]*)\]", label):
                        if notiz not in notizen:
                            notizen.append(notiz)
                if len(info["labels"]) > 6:
                    sauber.append("…")
                dazu(f"{einzug}   " + "  /  ".join(sauber), "bestimmung")
                for notiz in notizen:
                    dazu(f"{einzug}   ({notiz})", "leise")
            elif info["lemma"]:
                dazu(f"{einzug}   Grundform", "bestimmung")
        if deutsch_treffer:
            dazu(f"{einzug}   (über die deutsche Bedeutung gefunden)", "leise")
        for e in sorted(g["entries"], key=lambda x: x["lektion"]):
            dazu(f"{einzug}   [Lektion {e['lektion']}]  {e['deutsch']}", "normal")
            teile = [f"{FORMEN_LABEL.get(k, k)}: {v}" for k, v in e.get("formen", {}).items()]
            if teile:
                dazu(f"{einzug}      " + "  |  ".join(teile), "leise")
            zusatz = [f"{b} {e[s]}" for s, b in (("genus", "Genus"), ("deklination", "Deklination"),
                                                 ("numerus", "nur"), ("kasus", "Kasus"))
                      if e.get(s)]
            if zusatz:
                dazu(f"{einzug}      " + "  |  ".join(zusatz), "leise")
        return stuecke

    def suche(self, d):
        wort = str(d.get("q", "")).strip()
        if not wort:
            return {"stuecke": []}
        res = self.db.search(wort)
        stuecke = []
        lat = res["latein"]
        if lat:
            stuecke.append({"t": "LATEINISCH", "k": "abschnitt"})
            for gid, info in sorted(lat.items(), key=lambda kv: not kv[1]["lemma"]):
                stuecke += self._gruppe_stuecke(gid, info)
        if res["deutsch"]:
            gezeigt = 0
            for gid, _typ in res["deutsch"]:
                if gid in lat:
                    continue
                if gezeigt == 0:
                    stuecke.append({"t": "DEUTSCHE BEDEUTUNG", "k": "abschnitt"})
                stuecke += self._gruppe_stuecke(gid, None, deutsch_treffer=True)
                gezeigt += 1
                if gezeigt >= 12:
                    stuecke.append({"t": "   … weitere Treffer nicht angezeigt", "k": "leise"})
                    break
        if res["woerter"]:
            stuecke.append({"t": "WORT FÜR WORT", "k": "abschnitt"})
            for tok, treffer in res["woerter"]:
                stuecke.append({"t": f"   ▸ {tok}", "k": "normal"})
                for gid, info in treffer.items():
                    stuecke += self._gruppe_stuecke(gid, info, einzug="   ")
        if res["wendungen"]:
            stuecke.append({"t": "KOMMT AUSSERDEM VOR IN", "k": "abschnitt"})
            for gid in res["wendungen"][:8]:
                g = self.db.groups[gid]
                e = g["entries"][0]
                stuecke.append({"t": f"   {g['lemma']}  –  {e['deutsch']}  [Lektion {e['lektion']}]",
                                "k": "normal"})
        if not stuecke:
            stuecke.append({"t": f"Keine Vokabel zu „{wort}“ gefunden.", "k": "titel"})
            if res["vorschlaege"]:
                stuecke.append({"t": "MEINTEST DU VIELLEICHT", "k": "abschnitt"})
                for gid, wert, text in res["vorschlaege"]:
                    stuecke.append({"t": f"   {text}    [{int(wert * 100)} %]", "k": "normal",
                                    "g": gid if self.db.groups[gid].get("par") else None})
            else:
                stuecke.append({"t": "Auch keine ähnlichen Wörter gefunden.", "k": "leise"})
        return {"stuecke": stuecke}

    def formen(self, d):
        g = self.db.groups[int(d["gid"])]
        gruppiert = {}
        for label, person, alts in g["par"].rows:
            voll = label + (", " + person if person else "")
            gruppiert.setdefault(label, []).append((voll[len(label):].strip(", "),
                                                    " / ".join(alts)))
        return {"titel": f"{g['lemma']}   ({g['wortart']})",
                "gruppen": [{"label": label, "zeilen": zeilen}
                            for label, zeilen in gruppiert.items()]}

    # -------------------------------------------------- Fehlerliste
    def fehlerliste(self, d):
        archiv = str(d.get("archiv", "")) in ("1", "true", "True")
        zahlen = self.fehler.zahlen()
        zeilen = self.fehler.archiv() if archiv else self.fehler.aktive()
        return {"archiv": archiv, "offen": zahlen["offen"], "geschafft": zahlen["geschafft"],
                "ziel": FD.ZIEL_PUNKTE, "fuss": self.fuss(),
                "zeilen": [{"k": k, "fortschritt": self.fehler.fortschritt(v),
                            "latein": v["latein"], "deutsch": v["deutsch"],
                            "lektion": v["lektion"], "falsch": v["falsch"],
                            "richtig": v["richtig"]} for k, v in zeilen]}

    def fehler_zuruecksetzen(self, d):
        self.fehler.zuruecksetzen(d["k"])
        return self.fehlerliste(d)

    def fehler_entfernen(self, d):
        self.fehler.entfernen(d["k"])
        return self.fehlerliste(d)

    # -------------------------------------------------- Grammatik
    def grammatik(self, d):
        i = max(0, min(len(self.themen) - 1, int(d.get("i", 0))))
        name, schluessel = self.themen[i]
        seiten = GR.buchseiten(schluessel[1]) if schluessel[0] == "lektion" else []
        ungeprueft = schluessel[0] == "lektion" and GR.ist_ungeprueft(schluessel[1])
        tafeln = []
        for tafel in GR.tafeln(self.db, schluessel, self.neu):
            zeilen = tafel.text().splitlines()
            tafeln.append({"titel": zeilen[0], "warnung": zeilen[0].startswith("⚠"),
                           "text": "\n".join(zeilen[1:])})
        if ungeprueft:
            hinweis = (f"⚠ Zu Lektion {schluessel[1]} liegt keine Grammatikseite aus dem Buch "
                       f"vor – die Themen sind nur aus den Vokabeln abgeleitet und können vom "
                       f"Lehrbuch abweichen.")
        else:
            hinweis = ("Die Tabellen werden aus den Vokabeln erzeugt – ohne Längenzeichen, "
                       "weil die Formen aus dem Wortstamm gebildet werden.")
        return {"i": i, "name": name, "hinweis": hinweis, "ungeprueft": ungeprueft,
                "tafeln": tafeln, "seiten": [f"/bild/{p.name}" for p in seiten]}

    # -------------------------------------------------- Alle Vokabeln
    def vokabeln(self, d):
        gewaehlt = str(d.get("lektion", "alle"))
        nur = int(gewaehlt) if gewaehlt.isdigit() else None
        text = str(d.get("filter", "")).strip().lower()
        sortierung = d.get("sort", "lektion")
        if sortierung not in SPALTEN_NAMEN:
            sortierung = "lektion"
        zeilen = []
        for g in self.db.groups:
            for e in g["entries"]:
                if nur is not None and e["lektion"] != nur:
                    continue
                latein = quiz.grundform(g, e)
                if text:
                    heu = f"{latein} {e['latein']} {e['deutsch']}".lower()
                    if text not in heu and norm(text) not in norm(heu):
                        continue
                zeilen.append({"lektion": e["lektion"], "latein": latein,
                               "wortart": g["wortart"], "deutsch": e["deutsch"],
                               "formen": quiz.stammformen(g, e), "roh": e["latein"]})

        def schluessel(z):
            if sortierung == "lektion":
                return (z["lektion"], norm(z["latein"]))
            if sortierung == "latein":
                return (norm(z["latein"]), z["lektion"])
            if sortierung == "deutsch":
                return (z["deutsch"].lower(), z["lektion"])
            if sortierung == "wortart":
                ordnung = (WORTART_ORDER.index(z["wortart"])
                           if z["wortart"] in WORTART_ORDER else 99)
                return (ordnung, z["lektion"], norm(z["latein"]))
            return (z["formen"].lower(), z["lektion"])

        zeilen.sort(key=schluessel, reverse=str(d.get("ab", "")) in ("1", "true", "True"))
        return {"zeilen": zeilen, "gesamt": len(self.db.entries),
                "sortiert": SPALTEN_NAMEN[sortierung]}


# --------------------------------------------------------------------------
#  Webserver
# --------------------------------------------------------------------------

_bereit = threading.Event()
_sperre = threading.Lock()
_trainer = None
_ladefehler = None


def _laden():
    global _trainer, _ladefehler
    try:
        _trainer = Trainer()
    except Exception:
        _ladefehler = traceback.format_exc()
    _bereit.set()


class Anfrage(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        self._bearbeiten()

    def do_POST(self):
        self._bearbeiten()

    def _senden(self, status, inhalt, art, zwischenspeichern=False):
        self.send_response(status)
        self.send_header("Content-Type", art)
        self.send_header("Content-Length", str(len(inhalt)))
        self.send_header("Cache-Control", "max-age=86400" if zwischenspeichern else "no-store")
        self.end_headers()
        self.wfile.write(inhalt)

    def _json(self, status, daten):
        self._senden(status, json.dumps(daten, ensure_ascii=False).encode("utf-8"),
                     "application/json; charset=utf-8")

    def _bearbeiten(self):
        url = urlparse(self.path)
        pfad = unquote(url.path)
        if pfad in ("/", "/index.html"):
            return self._senden(200, OBERFLAECHE.read_bytes(), "text/html; charset=utf-8")
        if pfad.startswith("/bild/"):
            name = pfad[len("/bild/"):]
            datei = pfade.GRAMMATIK_BILDER / name
            if Path(name).name != name or datei.suffix.lower() != ".jpg" or not datei.is_file():
                return self._senden(404, b"", "text/plain")
            return self._senden(200, datei.read_bytes(), "image/jpeg", zwischenspeichern=True)
        if not pfad.startswith("/api/"):
            return self._senden(404, b"", "text/plain")

        daten = {k: v[-1] for k, v in parse_qs(url.query).items()}
        laenge = int(self.headers.get("Content-Length") or 0)
        if laenge:
            try:
                daten.update(json.loads(self.rfile.read(laenge)))
            except ValueError:
                return self._json(400, {"absturz": "Ungültige Anfrage."})
        _bereit.wait()
        if _ladefehler:
            return self._json(500, {"absturz": "Die Vokabeln konnten nicht geladen werden.\n\n"
                                               + _ladefehler})
        aktion = _trainer.aktionen.get(pfad[len("/api/"):])
        if aktion is None:
            return self._json(404, {"absturz": f"Unbekannt: {pfad}"})
        try:
            with _sperre:
                antwort = aktion(daten)
        except Exception:
            return self._json(500, {"absturz": traceback.format_exc()})
        self._json(200, antwort)


def starten(port=0):
    """Startet Laden und Server im Hintergrund.  Gibt die Adresse zurueck."""
    threading.Thread(target=_laden, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", port), Anfrage)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}/"


def main():
    adresse = starten(8765)
    print(f"Handy-Oberflaeche laeuft:  {adresse}   (Beenden mit Strg+C)")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())
