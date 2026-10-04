"""
saetze.py  -  Übersetzungssätze für den Reiter „Sätze“ (Beta)
=============================================================
Die Sätze stehen in daten/saetze.txt (Format siehe dort).  Hier werden sie
gelesen, Wort für Wort mit der Formerkennung zerlegt und einer Lektion
zugeordnet:

    Lektion eines Satzes = spätestes Wort bzw. spätere Form (Perfekt erst ab
    L8, Passiv ab L13 ...) - mindestens aber die Grammatik-Lektion aus der
    Kopfzeile in saetze.txt.

Ausserdem: eine grobe Bewertung deutscher Übersetzungen (Wortvergleich mit
den Musterlösungen) und die Wortanalyse zum Antippen.

Prüfen der ganzen Sammlung:

    py -3 programm/saetze.py            Fehler und Warnungen
    py -3 programm/saetze.py -v         dazu jeden Satz mit seiner Lektion
"""

import random
import re
import sys
from difflib import SequenceMatcher

import pfade
import vokabel_search as quiz
from bettervokable_search import norm

DATEI = pfade.DATEN / "saetze.txt"
WORT = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿĀ-ſ]+")
LETZTE_MERKEN = 40                 # so viele Stücke nicht gleich wiederholen

# Formen aus dem Perfektstamm bzw. mit PPP - die lernt man erst mit der
# Stammform, die das Buch beim Wort angibt.
PERFEKTSTAMM = ("Perfekt Aktiv", "Plusquamperfekt", "Futur II", "Infinitiv Perfekt Aktiv")
PPP_FORMEN = ("PPP", "Perfekt Passiv", "Plusquamperfekt Passiv", "Infinitiv Perfekt Passiv")

# Das v-Perfekt der a-Konjugation ist regelmäßig (vocāvī, laudāvī) - das Buch
# gibt es bei den frühen Verben nur nicht eigens an.  Ausnahmen:
A_PERFEKT_UNREGELMAESSIG = {"dare", "stare", "instare", "circumdare"}

# Wörter, die das Buch in der Grammatik oder als Wendung lehrt, die aber nicht
# einzeln in vokabel_base.json stehen:  Form -> (Lektion, Grundform, Wortart,
# Bedeutung, Bestimmung)
EXTRA = {
    "se": (12, "sē", "Pronomen", "sich", "Reflexivpronomen, Akkusativ"),
    "sibi": (12, "sibi", "Pronomen", "sich, für sich", "Reflexivpronomen, Dativ"),
    "salve": (3, "Salvē!", "Wendung", "Sei gegrüßt!", "Imperativ Sg."),
    "salvete": (3, "Salvēte!", "Wendung", "Seid gegrüßt!", "Imperativ Pl."),
    # Wendungen, deren gebeugte Formen die Formerkennung nicht kennt
    "circum maximum": (3, "Circus Maximus", "Substantiv", "der Circus Maximus", "Akkusativ Sg."),
    "circo maximo": (4, "Circus Maximus", "Substantiv", "der Circus Maximus", "Ablativ Sg."),
}
EXTRA = {norm(k): v for k, v in EXTRA.items()}


class Satz:
    def __init__(self, la):
        self.la = la
        self.de = []               # Musterlösungen
        self.woerter = []          # [{"t": "Servus", "l": 1, ...}] nach dem Laden
        self.lektion = 1


class Stueck:
    def __init__(self, nummer, grammatik, titel, text, zeile):
        self.nummer = nummer
        self.grammatik = grammatik
        self.titel = titel
        self.text = text
        self.zeile = zeile
        self.saetze = []
        self.lektion = grammatik

    def daten(self):
        return {"id": self.nummer, "titel": self.titel, "text": self.text,
                "lektion": self.lektion,
                "saetze": [{"la": s.la, "woerter": [w["t"] for w in s.woerter]}
                           for s in self.saetze]}


# --------------------------------------------------------------------------
#  Einlesen
# --------------------------------------------------------------------------

def lesen(pfad=DATEI):
    """saetze.txt -> [Stueck] (noch ohne Lektionsberechnung)."""
    stuecke, fehler = [], []
    modus, grammatik, aktuell = None, 1, None
    try:
        zeilen = pfad.read_text(encoding="utf-8").splitlines()
    except OSError as ex:
        return [], [f"{pfad}: {ex}"]
    for nr, zeile in enumerate(zeilen, 1):
        z = zeile.strip()
        if not z or z.startswith("#"):
            continue
        kopf = re.match(r"^(--|==)\s*L(\d+)\s*(.*)$", z)
        if kopf:
            modus, grammatik = kopf.group(1), int(kopf.group(2))
            aktuell = None
            if modus == "==":
                aktuell = Stueck(len(stuecke), grammatik, kopf.group(3).strip(), True, nr)
                stuecke.append(aktuell)
            continue
        if z.startswith("la:"):
            if modus is None:
                fehler.append(f"Zeile {nr}: „la:“ vor der ersten Kopfzeile")
                continue
            if modus == "--":
                aktuell = Stueck(len(stuecke), grammatik, "", False, nr)
                stuecke.append(aktuell)
            aktuell.saetze.append(Satz(z[3:].strip()))
        elif z.startswith("de:"):
            if not aktuell or not aktuell.saetze or aktuell.saetze[-1].de:
                fehler.append(f"Zeile {nr}: „de:“ ohne passende „la:“-Zeile")
                continue
            aktuell.saetze[-1].de = [v.strip() for v in z[3:].split("|") if v.strip()]
        else:
            fehler.append(f"Zeile {nr}: unverständlich: {z[:50]}")
    for st in stuecke:
        for s in st.saetze:
            if not s.de:
                fehler.append(f"Zeile {st.zeile}: „{s.la}“ hat keine Übersetzung")
    return stuecke, fehler


# --------------------------------------------------------------------------
#  Wortanalyse und Lektion
# --------------------------------------------------------------------------

def _stammform_lektion(gruppe, schluessel):
    """Erste Lektion, in der das Buch diese Stammform (perfekt/ppp) angibt."""
    ls = [e["lektion"] for e in gruppe["entries"] if (e.get("formen") or {}).get(schluessel)]
    return min(ls) if ls else None


def _a_perfekt(gruppe, wort):
    """Regelmäßiges v-Perfekt eines Verbs der a-Konjugation?"""
    inf = norm(gruppe.get("inf") or gruppe["lemma"])
    return (gruppe["wortart"] == "Verb" and inf.endswith("are")
            and inf not in A_PERFEKT_UNREGELMAESSIG and "av" in wort.lower().replace("ā", "a"))


def analysen(db, wort):
    """Alle Deutungen eines Wortes (oder einer Wendung):
    [{"gid", "lemma", "wortart", "deutsch", "bestimmung", "lektion", "ungeprueft"}]"""
    treffer = db.search(wort)["latein"]
    ergebnis = []
    for gid, info in treffer.items():
        g = db.groups[gid]
        eintraege = sorted(g["entries"], key=lambda e: e["lektion"])
        erste = eintraege[0]["lektion"]
        basis = {"gid": gid, "lemma": quiz.grundform(g, eintraege[0]),
                 "wortart": g["wortart"], "deutsch": eintraege[0]["deutsch"],
                 "angehaengt": info.get("enclitic") or ""}
        if info["lemma"]:
            ergebnis.append(dict(basis, bestimmung="Grundform", lektion=erste, ungeprueft=False))
        for label in info["labels"]:
            sauber = quiz.sauberes_label(label)
            lektion = max(erste, quiz.form_lektion(sauber))
            ungeprueft = "ungeprüft" in label
            if ungeprueft and any(sauber.startswith(a) for a in PERFEKTSTAMM)                     and _stammform_lektion(g, "perfekt") is None and _a_perfekt(g, wort):
                ungeprueft = False
            for anfaenge, schluessel in ((PERFEKTSTAMM, "perfekt"), (PPP_FORMEN, "ppp")):
                if any(sauber.startswith(a) for a in anfaenge):
                    stamm = _stammform_lektion(g, schluessel)
                    if stamm is not None:
                        lektion = max(lektion, stamm)
                    elif not (schluessel == "perfekt" and _a_perfekt(g, wort)):
                        ungeprueft = True
            ergebnis.append(dict(basis, bestimmung=sauber, lektion=lektion,
                                 ungeprueft=ungeprueft))
    extra = EXTRA.get(norm(wort))
    if extra:
        lektion, lemma, wortart, deutsch, bestimmung = extra
        ergebnis.append({"gid": None, "lemma": lemma, "wortart": wortart, "deutsch": deutsch,
                         "angehaengt": "", "bestimmung": bestimmung, "lektion": lektion,
                         "ungeprueft": False})
    ergebnis.sort(key=lambda a: (a["ungeprueft"], a["lektion"]))
    return ergebnis


def zerlegen(db, la):
    """Satz -> Wörter mit Lektion.  Wendungen aus mehreren Wörtern (res
    publica, magna voce, Circus Maximus) werden zusammen erkannt."""
    toks = WORT.findall(la)
    woerter, i = [], 0
    while i < len(toks):
        for laenge in (3, 2, 1):
            stueck = " ".join(toks[i:i + laenge])
            if laenge > 1 and i + laenge > len(toks):
                continue
            deutungen = analysen(db, stueck)
            if deutungen or laenge == 1:
                break
        beste = deutungen[0] if deutungen else None
        woerter.append({"t": stueck, "n": laenge,
                        "l": beste["lektion"] if beste else None,
                        "ungeprueft": bool(beste and beste["ungeprueft"]),
                        "deutung": beste, "alle": deutungen})
        i += laenge
    return woerter


def laden(db, pfad=DATEI):
    """Liest saetze.txt und berechnet die Lektionen.  -> (stuecke, fehler)"""
    stuecke, fehler = lesen(pfad)
    for st in stuecke:
        st.lektion = st.grammatik
        for s in st.saetze:
            s.woerter = zerlegen(db, s.la)
            bekannt = [w["l"] for w in s.woerter if w["l"] is not None]
            s.lektion = max([st.grammatik] + bekannt)
            st.lektion = max(st.lektion, s.lektion)
    return stuecke, fehler


# --------------------------------------------------------------------------
#  Bewertung einer deutschen Übersetzung
# --------------------------------------------------------------------------

ARTIKEL = {"der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem",
           "einer", "eines"}
ENDUNGEN = ("ern", "em", "en", "er", "es", "e", "n", "s")


def _gnorm(text):
    text = text.lower().replace("ß", "ss")
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue")):
        text = text.replace(a, b)
    return re.findall(r"[a-z]+", text)


def _stamm(w):
    for e in ENDUNGEN:
        if w.endswith(e) and len(w) - len(e) >= 4:
            return w[:-len(e)]
    return w


def _passt(a, b):
    """a, b normalisierte Wörter: gleich, gleicher Stamm oder nur ein Tippfehler."""
    if a == b:
        return 2
    if _stamm(a) == _stamm(b):
        return 1
    if min(len(a), len(b)) >= 5 and SequenceMatcher(None, a, b).ratio() >= 0.8:
        return 1
    return 0


def synonyme(deutsch):
    """'der Sklave, der Diener' -> {'sklave', 'diener'}: alle Bedeutungswörter
    einer Vokabel - wer eine andere Bedeutung derselben Vokabel wählt, hat
    nicht falsch übersetzt."""
    text = re.sub(r"\((?:m\.|jdm|jdn|etw)[^)]*\)", " ", deutsch)
    return {w for w in _gnorm(text) if w not in ARTIKEL and len(w) > 2}


def _vergleich(antwort, variante, gruppen=()):
    noetig_text = re.sub(r"\([^)]*\)", " ", variante)
    noetig = [w for w in _gnorm(noetig_text) if w not in ARTIKEL]
    eigene = [w for w in _gnorm(antwort) if w not in ARTIKEL]
    frei = list(eigene)
    treffer, genau, fehlend = 0, True, []
    for w in noetig:
        beste, wo = 0, None
        for i, e in enumerate(frei):
            p = _passt(e, w)
            if p > beste:
                beste, wo = p, i
                if p == 2:
                    break
        if not beste:
            # eine andere Bedeutung derselben Vokabel?
            for gruppe in gruppen:
                if not any(_passt(w, g) for g in gruppe):
                    continue
                for i, e in enumerate(frei):
                    if any(_passt(e, g) for g in gruppe):
                        beste, wo = 1, i
                        break
                if beste:
                    break
        if beste:
            treffer += 1
            genau = genau and beste == 2
            frei.pop(wo)
        else:
            genau = False
            fehlend.append(w)
    anteil = treffer / len(noetig) if noetig else 1.0
    return anteil, genau, fehlend


def bewerten(antwort, varianten, gruppen=()):
    """-> {"bewertung", "anteil", "fehlend", "loesung"} - grob, nur Wortvergleich.
    Wortstellung und Satzbau prüft das nicht."""
    beste = None
    for v in varianten:
        anteil, genau, fehlend = _vergleich(antwort, v, gruppen)
        schluessel = (anteil, genau)
        if beste is None or schluessel > beste[0]:
            beste = (schluessel, v, fehlend)
    (anteil, genau), loesung, fehlend = beste
    if not antwort.strip():
        bewertung = "falsch"
    elif anteil >= 0.999:
        bewertung = "perfekt" if genau else "richtig"
    elif anteil >= 0.75:
        bewertung = "fast"
    elif anteil >= 0.4:
        bewertung = "teilweise"
    else:
        bewertung = "falsch"
    # fehlende Wörter in ihrer Originalschreibweise zeigen
    original = {}
    for w in re.findall(r"[^\W\d_]+", re.sub(r"\([^)]*\)", " ", loesung)):
        original.setdefault(_gnorm(w)[0] if _gnorm(w) else w, w)
    return {"bewertung": bewertung, "anteil": round(anteil * 100),
            "fehlend": [original.get(w, w) for w in fehlend], "loesung": loesung}


# --------------------------------------------------------------------------
#  Für den Server
# --------------------------------------------------------------------------

class Saetze:
    """Hält die Sammlung; eine Instanz für alle (in handy_server.Grundlage)."""

    def __init__(self, db, pfad=DATEI):
        self.db = db
        self.stuecke, self.fehler = laden(db, pfad)

    def zahlen(self):
        """{Lektion: Anzahl Stücke}"""
        z = {}
        for st in self.stuecke:
            z[st.lektion] = z.get(st.lektion, 0) + 1
        return z

    def auswahl(self, lektionen, art):
        return [st for st in self.stuecke if st.lektion in lektionen
                and (art == "gemischt" or (art == "text") == st.text)]

    def ziehen(self, lektionen, art, zuletzt):
        kandidaten = self.auswahl(lektionen, art)
        if not kandidaten:
            return None
        frisch = [st for st in kandidaten if st.nummer not in zuletzt]
        st = random.choice(frisch or kandidaten)
        zuletzt.append(st.nummer)
        del zuletzt[:-LETZTE_MERKEN]
        return st

    def pruefen(self, nummer, satz, antwort):
        st = self.stuecke[nummer]
        s = st.saetze[satz]
        gruppen = [synonyme(d["deutsch"]) for w in s.woerter for d in (w.get("alle") or [])]
        ergebnis = bewerten(antwort, s.de, [g for g in gruppen if len(g) > 1])
        ergebnis["varianten"] = [v for v in s.de if v != ergebnis["loesung"]]
        ergebnis["woerter"] = [self._wort_kurz(w) for w in s.woerter]
        return ergebnis

    def _wort_kurz(self, w):
        """Ein Wort für die Wort-für-Wort-Liste: bei mehrdeutigen Formen alle
        Grundformen (z. B. isti: iste / ire), je mit der ersten Bestimmung."""
        deutungen = {}
        for d in w.get("alle") or []:
            x = deutungen.setdefault(d["lemma"], {"lemma": d["lemma"], "deutsch": d["deutsch"],
                                                  "bestimmungen": []})
            b = "Grundform" if d["bestimmung"] == "Grundform" else d["bestimmung"]
            if b not in x["bestimmungen"]:
                x["bestimmungen"].append(b)
        liste = []
        for x in list(deutungen.values())[:3]:
            bs = [b for b in x["bestimmungen"] if b != "Grundform"] or []
            liste.append({"lemma": x["lemma"], "deutsch": x["deutsch"],
                          "bestimmung": " / ".join(bs[:4]) + (" / …" if len(bs) > 4 else "")})
        return {"t": w["t"], "deutungen": liste}

    def wort(self, wort):
        deutungen = analysen(self.db, wort)
        gesehen, liste = set(), []
        for d in deutungen:
            k = (d["gid"], d["bestimmung"])
            if k in gesehen:
                continue
            gesehen.add(k)
            liste.append({"lemma": d["lemma"], "wortart": d["wortart"], "deutsch": d["deutsch"],
                          "bestimmung": d["bestimmung"], "lektion": d["lektion"],
                          "angehaengt": d["angehaengt"],
                          "gid": d["gid"] if d["gid"] is not None
                          and self.db.groups[d["gid"]].get("par") else None})
        return {"wort": wort, "deutungen": liste[:8]}


# --------------------------------------------------------------------------
#  Prüfen der Sammlung
# --------------------------------------------------------------------------

def main():
    from bettervokable_search import VokabelBase
    ausfuehrlich = "-v" in sys.argv
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    db = VokabelBase()
    stuecke, fehler = laden(db)
    warnungen = []
    for st in stuecke:
        for s in st.saetze:
            for w in s.woerter:
                if w["l"] is None:
                    fehler.append(f"Zeile {st.zeile}: „{w['t']}“ unbekannt  –  {s.la}")
                elif w["ungeprueft"]:
                    warnungen.append(f"Zeile {st.zeile}: „{w['t']}“ nur ungeprüft erkannt "
                                     f"({w['deutung']['bestimmung']})  –  {s.la}")
            if s.lektion > st.grammatik + 3 and not st.text:
                warnungen.append(f"Zeile {st.zeile}: steht bei L{st.grammatik}, gilt aber erst "
                                 f"ab L{s.lektion}  –  {s.la}  "
                                 + ", ".join(f"{w['t']}=L{w['l']}" for w in s.woerter
                                             if w["l"] and w["l"] > st.grammatik))
            if ausfuehrlich:
                print(f"L{s.lektion:>2}  {s.la}   "
                      + " ".join(f"[{w['t']}:{w['l']}]" for w in s.woerter))
    z = {}
    for st in stuecke:
        z[st.lektion] = z.get(st.lektion, 0) + 1
    print(f"{len(stuecke)} Stücke, {sum(len(st.saetze) for st in stuecke)} Sätze, "
          f"{sum(st.text for st in stuecke)} Texte")
    print("je Lektion: " + "  ".join(f"L{k}:{v}" for k, v in sorted(z.items())))
    for w in warnungen:
        print("WARNUNG", w)
    for f in fehler:
        print("FEHLER ", f)
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
