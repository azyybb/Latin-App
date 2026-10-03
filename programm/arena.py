"""
arena.py  -  Online-Quiz gegeneinander (wie Kahoot)
===================================================
Einer erstellt eine Arena und bekommt einen vierstelligen Code, die anderen
treten mit dem Code bei und waehlen einen Namen.  Der Ersteller startet eine
Runde, wann er will; jeder beantwortet die Fragen auf seinem eigenen Geraet
in seinem Tempo.  Schnelle richtige Antworten bringen mehr Punkte.  Nach der
Runde gibt es ein Scoreboard und alle bleiben in der Arena fuer die naechste.

Nur auf der Website (web_server.py) - jeder Spieler ist dort ueber seinen
Lerncode bekannt, Antworten landen wie im normalen Quiz in seiner
Fehlerliste und Statistik.

Alles liegt nur im Speicher: ein Neustart des Servers beendet die Arenen.
Aufgerufen wird nur unter der Sperre von web_server.py.
"""

import random
import time

import handy_server as HS
import vokabel_search as quiz

LEBENSDAUER = 3 * 3600         # Arena ohne Aktivitaet so lange behalten
OFFLINE_NACH = 45              # Sekunden ohne Abfrage -> gilt als weg
HOST_WECHSEL_NACH = 90         # Ersteller so lange weg -> anderer uebernimmt
GROESSTE_ARENA = 60
NAME_LAENGE = 20
VOLLE_PUNKTE_BIS = 3           # Sekunden
HALBE_PUNKTE_AB = 30


def punkte_fuer(bewertung, sekunden):
    """Richtig gibt 400-800, perfekt 500-1000 Punkte - je schneller, desto mehr."""
    if bewertung == quiz.FALSCH:
        return 0
    basis = 1000 if bewertung == quiz.PERFEKT else 800
    anteil = (sekunden - VOLLE_PUNKTE_BIS) / (HALBE_PUNKTE_AB - VOLLE_PUNKTE_BIS)
    schnell = 1 - max(0.0, min(1.0, anteil))
    return round(basis * (0.5 + 0.5 * schnell))


def modus_text(d, gleich, quelle, anzahl):
    modus = {"ld": "Latein → Deutsch", "dl": "Deutsch → Latein", "mix": "gemischt",
             "formen": "Formen-Quiz"}.get(d.get("modus"), "Latein → Deutsch")
    teile = [f"{anzahl} Fragen" if anzahl else "Fragen", modus]
    teile.append("eigene Fehlervokabeln" if quelle == "fehler"
                 else f"Lektionen {d.get('lektionen') or 'alle'}")
    teile.append("alle die gleichen Fragen" if gleich else "jeder andere Fragen")
    if not d.get("mitspielen", True):
        teile.append("Ersteller schaut zu")
    return "  ·  ".join(teile)


class Runde:
    """Fortschritt eines Spielers in der laufenden Runde."""

    def __init__(self, aufgaben):
        self.aufgaben = aufgaben             # [(gruppe, eintrag, frage), ...]
        self.nummer = 0                      # beantwortete Fragen
        self.phase = "frage" if aufgaben else "fertig"
        self.seit = time.monotonic()
        self.punkte = 0
        self.zaehler = {quiz.PERFEKT: 0, quiz.RICHTIG: 0, quiz.FALSCH: 0}
        self.rueckmeldung = {}

    @property
    def durch(self):
        """Alle Fragen beantwortet (die letzte Rueckmeldung kann noch offen sein)."""
        return self.nummer >= len(self.aufgaben)

    @property
    def fertig(self):
        return self.phase == "fertig"


class Spieler:
    def __init__(self, code, name):
        self.code = code
        self.name = name
        self.gesamt = 0
        self.runde = None
        self.zuletzt = time.monotonic()

    @property
    def online(self):
        return time.monotonic() - self.zuletzt < OFFLINE_NACH


class Raum:
    def __init__(self, code, host):
        self.code = code
        self.host = host
        self.spieler = {}                    # Lerncode -> Spieler, in Beitrittsfolge
        self.phase = "lobby"
        self.rundennummer = 0
        self.beschreibung = ""
        self.ergebnis = None
        self.zuletzt = time.monotonic()


class Arena:
    def __init__(self, trainer_fuer):
        self.trainer_fuer = trainer_fuer     # Lerncode -> Trainer
        self.raeume = {}                     # "4821" -> Raum
        self.wo = {}                         # Lerncode -> Raumcode
        self.aktionen = {
            "erstellen": self.erstellen, "beitreten": self.beitreten,
            "name": self.name_aendern, "verlassen": self.verlassen,
            "starten": self.starten, "antworten": self.antworten,
            "weiter": self.weiter, "beenden": self.beenden, "zustand": self.zustand,
        }

    # -------------------------------------------------- Verwaltung
    def _aufraeumen(self):
        jetzt = time.monotonic()
        for code, raum in list(self.raeume.items()):
            if not raum.spieler or jetzt - raum.zuletzt > LEBENSDAUER:
                for s in raum.spieler:
                    self.wo.pop(s, None)
                del self.raeume[code]

    def _mein_raum(self, code):
        raum = self.raeume.get(self.wo.get(code))
        if raum is None or code not in raum.spieler:
            self.wo.pop(code, None)
            return None, None
        return raum, raum.spieler[code]

    def _name(self, raum, wunsch, ich=None):
        name = " ".join(str(wunsch or "").split())[:NAME_LAENGE]
        if not name:
            name = f"Spieler {len(raum.spieler) + (0 if ich else 1)}"
        vergeben = {s.name.lower() for k, s in raum.spieler.items() if k != ich}
        basis, n = name, 2
        while name.lower() in vergeben:
            name = f"{basis[:NAME_LAENGE - 3]} {n}"
            n += 1
        return name

    def _neuer_code(self):
        frei = [f"{n:04d}" for n in range(1000, 10000) if f"{n:04d}" not in self.raeume]
        return random.choice(frei) if frei else None

    def _verlassen(self, code):
        raum, _s = self._mein_raum(code)
        if raum is None:
            return
        del raum.spieler[code]
        self.wo.pop(code, None)
        if raum.host == code and raum.spieler:
            online = [k for k, s in raum.spieler.items() if s.online]
            raum.host = (online or list(raum.spieler))[0]
        if not raum.spieler:
            del self.raeume[raum.code]
        else:
            self._runde_pruefen(raum)

    # -------------------------------------------------- Aktionen
    def erstellen(self, code, _t, d):
        self._aufraeumen()
        self._verlassen(code)
        raumcode = self._neuer_code()
        if raumcode is None:
            return {"fehler": "Gerade sind zu viele Arenen offen. Bitte später nochmal."}
        raum = self.raeume[raumcode] = Raum(raumcode, code)
        raum.spieler[code] = Spieler(code, self._name(raum, d.get("name")))
        self.wo[code] = raumcode
        return self.zustand(code, _t, d)

    def beitreten(self, code, _t, d):
        self._aufraeumen()
        raumcode = "".join(ch for ch in str(d.get("code", "")) if ch.isdigit())
        raum = self.raeume.get(raumcode)
        if raum is None:
            return {"fehler": "Zu diesem Code gibt es keine Arena."}
        if code in raum.spieler:
            raum.spieler[code].name = self._name(raum, d.get("name"), code)
            return self.zustand(code, _t, d)
        if len(raum.spieler) >= GROESSTE_ARENA:
            return {"fehler": "Diese Arena ist voll."}
        self._verlassen(code)
        raum.spieler[code] = Spieler(code, self._name(raum, d.get("name")))
        self.wo[code] = raumcode
        raum.zuletzt = time.monotonic()
        return self.zustand(code, _t, d)

    def name_aendern(self, code, t, d):
        raum, ich = self._mein_raum(code)
        if raum:
            ich.name = self._name(raum, d.get("name"), code)
        return self.zustand(code, t, d)

    def verlassen(self, code, t, d):
        self._verlassen(code)
        return self.zustand(code, t, d)

    def starten(self, code, t, d):
        raum, _ich = self._mein_raum(code)
        if raum is None:
            return self.zustand(code, t, d)
        if raum.host != code:
            return {"fehler": "Nur wer die Arena erstellt hat, kann starten."}
        gleich = bool(d.get("gleich", True))
        quelle = "fehler" if d.get("quelle") == "fehler" else "auswahl"
        if quelle == "fehler":
            gleich = False                   # jeder hat seine eigene Liste

        auswahl = HS.auswahl_lesen(t, d)
        if "fehler" in auswahl:
            return auswahl
        modus, formen = auswahl["modus"], auswahl["formen"]

        def bauen(paare, anzahl):
            aufgaben = []
            for gruppe, eintrag in HS.aufgaben_ziehen(paare, anzahl):
                frage = HS.aufgabe_bauen(t.db, gruppe, eintrag, modus, formen)
                if frage is not None:
                    aufgaben.append((gruppe, eintrag, frage))
            return aufgaben

        # Ohne Haken "Ich spiele mit" schaut der Ersteller nur zu (z. B. am Beamer)
        mitspielen = bool(d.get("mitspielen", True))
        teilnehmer = [s for s in raum.spieler.values()
                      if (s.online and s.code != code) or (s.code == code and mitspielen)]
        if not teilnehmer:
            return {"fehler": "Es ist noch niemand zum Mitspielen in der Arena."}
        gemeinsam = bauen(auswahl["paare"], auswahl["anzahl"]) if gleich else None
        for s in raum.spieler.values():
            s.runde = None
        for s in teilnehmer:
            if gleich:
                s.runde = Runde(list(gemeinsam))
                continue
            aufgaben = []
            if quelle == "fehler":
                eigene = self.trainer_fuer(s.code).fehler.paare(t.db)
                if eigene:
                    aufgaben = bauen(eigene, min(auswahl["anzahl"], len(eigene)))
            s.runde = Runde(aufgaben or bauen(auswahl["paare"], auswahl["anzahl"]))

        raum.phase = "runde"
        raum.rundennummer += 1
        raum.ergebnis = None
        raum.beschreibung = modus_text(d, gleich, quelle,
                                       None if quelle == "fehler" else auswahl["anzahl"])
        return self.zustand(code, t, d)

    def antworten(self, code, t, d):
        raum, ich = self._mein_raum(code)
        r = ich.runde if ich else None
        if raum and raum.phase == "runde" and r and r.phase == "frage":
            gruppe, eintrag, frage = r.aufgaben[r.nummer]
            antwort = str(d.get("antwort", "")).strip()[:200]
            sekunden = time.monotonic() - r.seit
            r.rueckmeldung = HS.antwort_bewerten(t, gruppe, eintrag, frage, antwort)
            bewertung = r.rueckmeldung["bewertung"]
            plus = punkte_fuer(bewertung, sekunden)
            r.rueckmeldung["plus"] = plus
            r.punkte += plus
            r.zaehler[bewertung] += 1
            r.nummer += 1
            r.phase = "antwort"
        return self.zustand(code, t, d)

    def weiter(self, code, t, d):
        raum, ich = self._mein_raum(code)
        r = ich.runde if ich else None
        if raum and r and r.phase == "antwort":
            r.phase = "fertig" if r.durch else "frage"
            r.rueckmeldung = {}
            r.seit = time.monotonic()
        return self.zustand(code, t, d)

    def beenden(self, code, t, d):
        raum, _ich = self._mein_raum(code)
        if raum and raum.host == code and raum.phase == "runde":
            self._abschliessen(raum)
        return self.zustand(code, t, d)

    # -------------------------------------------------- Rundenende
    def _runde_pruefen(self, raum):
        """Vorbei, wenn alle Teilnehmer fertig sind (wer weg ist, zaehlt als fertig)."""
        if raum.phase != "runde":
            return
        dabei = [s for s in raum.spieler.values() if s.runde]
        if all(s.runde.fertig or not s.online for s in dabei):
            self._abschliessen(raum)

    def _abschliessen(self, raum):
        zeilen = []
        for s in raum.spieler.values():
            r = s.runde
            if r is None:
                continue
            s.gesamt += r.punkte
            zeilen.append({"code": s.code, "name": s.name, "punkte": r.punkte,
                           "richtig": r.zaehler[quiz.PERFEKT] + r.zaehler[quiz.RICHTIG],
                           "gestellt": r.nummer, "fragen": len(r.aufgaben)})
            s.runde = None
        zeilen.sort(key=lambda z: (-z["punkte"], -z["richtig"], z["name"].lower()))
        platz = 0
        for i, z in enumerate(zeilen):
            if i == 0 or z["punkte"] != zeilen[i - 1]["punkte"]:
                platz = i + 1
            z["platz"] = platz
        raum.ergebnis = {"runde": raum.rundennummer, "zeilen": zeilen,
                         "beschreibung": raum.beschreibung}
        raum.phase = "lobby"

    # -------------------------------------------------- Zustand
    def zustand(self, code, _t=None, _d=None):
        raum, ich = self._mein_raum(code)
        if raum is None:
            return {"raum": None}
        jetzt = time.monotonic()
        ich.zuletzt = raum.zuletzt = jetzt
        host = raum.spieler.get(raum.host)
        if host is None or (jetzt - host.zuletzt > HOST_WECHSEL_NACH and ich is not host):
            raum.host = code                 # Ersteller ist weg -> wer da ist, uebernimmt
        self._runde_pruefen(raum)

        spieler = []
        for s in raum.spieler.values():
            r = s.runde
            if raum.phase == "runde" and r:
                status = "fertig" if r.fertig else f"{r.nummer}/{len(r.aufgaben)}"
            elif raum.phase == "runde":
                status = "schaut zu" if s.code == raum.host else "wartet auf die nächste Runde"
            else:
                status = ""
            spieler.append({"name": s.name, "host": s.code == raum.host, "ich": s is ich,
                            "online": s.online, "gesamt": s.gesamt, "status": status,
                            "punkte": r.punkte if r else None})
        if raum.phase == "runde":
            spieler.sort(key=lambda z: (z["punkte"] is None, -(z["punkte"] or 0)))
        daten = {"raum": raum.code, "phase": raum.phase, "runde": raum.rundennummer,
                 "host": raum.host == code, "name": ich.name, "spieler": spieler,
                 "hostname": raum.spieler[raum.host].name,
                 "beschreibung": raum.beschreibung, "mein": None, "ergebnis": None}
        if raum.ergebnis:
            e = dict(raum.ergebnis)
            e["zeilen"] = [dict({k: v for k, v in z.items() if k != "code"}, ich=z["code"] == code)
                           for z in e["zeilen"]]
            daten["ergebnis"] = e
        r = ich.runde
        if raum.phase == "runde" and r:
            mein = {"phase": r.phase, "nummer": r.nummer, "gesamt": len(r.aufgaben),
                    "punkte": r.punkte, "perfekt": r.zaehler[quiz.PERFEKT],
                    "richtig": r.zaehler[quiz.RICHTIG], "falsch": r.zaehler[quiz.FALSCH]}
            if r.phase in ("frage", "antwort"):
                index = r.nummer if r.phase == "frage" else r.nummer - 1
                frage = r.aufgaben[index][2]
                mein.update({k: frage[k] for k in ("frage", "untertitel", "zusatz")})
                mein.update(r.rueckmeldung)
            rangliste = sorted((s.runde.punkte for s in raum.spieler.values() if s.runde),
                               reverse=True)
            mein["platz"] = rangliste.index(r.punkte) + 1
            mein["von"] = len(rangliste)
            daten["mein"] = mein
        return daten
