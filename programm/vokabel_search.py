"""
vokabel_search.py  -  Vokabelquiz
=================================
Baut auf bettervokable_search.py auf und benutzt dessen Formenerkennung:

  * Latein -> Deutsch, Deutsch -> Latein oder gemischt
  * Auswahl nach Lektion und nach Wortart
  * Formen-Quiz ("rogare, 3. Pers. Pl. Perfekt?"  /  "Woher kommt rogaverunt?")
  * Die Antwort wird automatisch geprueft.  Es genuegt EINE der Bedeutungen;
    Gross-/Kleinschreibung, Artikel, Umlaute und Tippfehler sind egal.

Start:   py -3 vokabel_search.py
"""

import random
import re
import sys
from difflib import SequenceMatcher

import fehler_datenbank as FD
from bettervokable_search import (
    VokabelBase, WORTART_ORDER, german_phrases, latin_variants,
    CONJ_NAMES, GER_STOP, ask, emit, gnorm, norm, setup_console,
)

# Ab dieser Aehnlichkeit gilt eine Antwort trotz Tippfehlern als richtig.
TOLERANZ = 0.82
# Kurze Woerter sind schneller zufaellig aehnlich, dort etwas strenger.
TOLERANZ_KURZ = 0.85
KURZ = 5

JA = ("j", "ja", "y", "yes")
NEIN = ("n", "nein", "no")

# Bewertung einer Antwort
PERFEKT = "perfekt"      # Zeichen für Zeichen wie in der Lösung
RICHTIG = "richtig"      # inhaltlich richtig (Tippfehler, andere Reihenfolge, Teilmenge)
FALSCH = "falsch"

URTEIL = {PERFEKT: "   [*] Perfekt!", RICHTIG: "   [+] Richtig!", FALSCH: "   [-] Falsch."}


# --------------------------------------------------------------------------
#  Antwortpruefung
# --------------------------------------------------------------------------

def _aehnlich(a, b):
    return SequenceMatcher(None, a, b).ratio()


def _passt(eingabe, erlaubt):
    """Passt die Eingabe zu einer der erlaubten Antworten?

    Liefert (richtig, getroffene Antwort, exakt).  Tippfehler werden verziehen,
    bei kurzen Woertern strenger als bei langen.
    """
    if not eingabe:
        return False, None, False
    if eingabe in erlaubt:
        return True, eingabe, True
    beste, bestwert = None, 0.0
    for kandidat in erlaubt:
        wert = _aehnlich(eingabe, kandidat)
        if wert > bestwert:
            beste, bestwert = kandidat, wert
        # Der Anfangsbuchstabe muss stimmen.  Tippfehler treffen ihn fast nie,
        # verschiedene Woerter dagegen schon ("tragen" ist kein "fragen",
        # obwohl sich die beiden zu 83 % gleichen).
        if kandidat[:1] != eingabe[:1]:
            continue
        grenze = TOLERANZ_KURZ if min(len(kandidat), len(eingabe)) <= KURZ else TOLERANZ
        if wert >= grenze:
            return True, kandidat, False
    return False, beste, False


def _teile(antwort):
    """Antwort in einzelne Bedeutungen zerlegen (Komma, Schraegstrich, oder)."""
    roh = antwort.replace("/", ",").replace(";", ",").replace(" oder ", ",")
    return [t.strip() for t in roh.split(",") if t.strip()]


def _bedeutungen(text):
    """Deutsche Bedeutungen eines Textes - mit und ohne Schraegstrich-Trennung,
    damit "kommen zu/nach" sowohl als Ganzes als auch geteilt passt."""
    return german_phrases(text) | german_phrases(text.replace("/", ","))


def bedeutungsgruppen(deutsch):
    """Eine Gruppe je Bedeutung; in der Gruppe stehen deren Schreibweisen.

    "der Kopf, die Hauptstadt"  ->  [{"kopf"}, {"hauptstadt"}]
    Für "perfekt" muss jede Gruppe getroffen sein.
    """
    gruppen = []
    for roh in re.split(r"[;,]", deutsch):
        if not roh.strip():
            continue
        varianten = _bedeutungen(roh)
        varianten.discard("")
        if varianten:
            gruppen.append(varianten)
    return gruppen


def _inhaltswoerter(text):
    """Bedeutungstragende Wörter eines Textes, ohne Artikel und Füllwörter."""
    return [w for w in text.split() if w not in GER_STOP and len(w) > 1]


def _enthalten(gesucht, vorhanden):
    """Kommen alle Wörter von 'gesucht' in 'vorhanden' vor - in beliebiger
    Reihenfolge und mit Tippfehler-Toleranz?

    Damit zählt "der Kopf die Hauptstadt" (ohne Komma, andere Reihenfolge)
    genauso wie "die Hauptstadt, der Kopf".
    """
    if not gesucht:
        return False
    offen = list(vorhanden)
    for wort in gesucht:
        treffer = None
        for kandidat in offen:
            if kandidat == wort or _passt(kandidat, {wort})[0]:
                treffer = kandidat
                break
        if treffer is None:
            return False
        offen.remove(treffer)          # jedes Wort nur einmal verbrauchen
    return True


def pruefe_deutsch(antwort, eintrag, db=None, gruppe=None):
    """Bewertet eine deutsche Antwort.  Liefert (PERFEKT/RICHTIG/FALSCH, Treffer).

    Eine von mehreren Bedeutungen genügt.  Die Antwort läuft durch dieselbe
    Aufbereitung wie die Lösung, damit "der Sklave" und "Sklave" gleich
    behandelt werden.
    """
    erlaubt = _bedeutungen(eintrag["deutsch"])
    gegeben = _bedeutungen(antwort.replace(" oder ", ","))

    # 1) "perfekt" nur, wenn JEDE Bedeutung der Lösung genau getroffen ist
    gruppen = bedeutungsgruppen(eintrag["deutsch"])
    if gruppen and all(g & gegeben for g in gruppen):
        return PERFEKT, eintrag["deutsch"]

    # 2) Bedeutung für Bedeutung - exakt oder mit Tippfehler
    bestes = FALSCH
    bester_treffer = None
    for teil in gegeben:
        ok, treffer, exakt = _passt(teil, erlaubt)
        if not ok:
            continue
        if not exakt and db is not None and gruppe is not None:
            # "stehen" gleicht "sehen" zu 91 % - aber es ist die Bedeutung
            # einer eigenen Vokabel und damit kein Tippfehler.
            fremd = db.ger_phrase.get(teil)
            if fremd and gruppe["id"] not in fremd:
                continue
        bestes, bester_treffer = RICHTIG, treffer
        break
    if bestes == RICHTIG:
        return bestes, bester_treffer

    # 2) Alle Wörter einer Bedeutung irgendwo in der Antwort - ohne Rücksicht
    #    auf Reihenfolge und Kommas ("der Kopf die Hauptstadt")
    gesamt = _inhaltswoerter(gnorm(antwort.replace("/", " ").replace(",", " ")))
    if gesamt:
        for bedeutung in sorted(erlaubt, key=len, reverse=True):
            if _enthalten(_inhaltswoerter(bedeutung), gesamt):
                return RICHTIG, bedeutung
    return FALSCH, None


def grundform(gruppe, eintrag):
    """Die Zitierform mit Längenzeichen (Infinitiv / Nominativ / m.)."""
    formen = eintrag.get("formen") or {}
    wortart = gruppe["wortart"]
    if wortart == "Verb":
        return formen.get("infinitiv") or eintrag["latein"]
    if wortart == "Substantiv":
        return formen.get("nominativ") or eintrag["latein"]
    if wortart == "Adjektiv":
        return formen.get("m") or eintrag["latein"]
    return eintrag["latein"]


def stammformen(gruppe, eintrag):
    """Die wichtigsten Angaben einer Vokabel in einer Zeile.

        Substantiv  servus, Gen. servī  ·  m  ·  2. Deklination
        Verb        rogō, rogāre, rogāvī, rogātum  ·  a-Konjugation
        Adjektiv    altus, alta, altum
    """
    # Der eigene Eintrag zuerst, fehlende Angaben aus den anderen Lektionen
    # derselben Vokabel ergänzen (videre steht in Lektion 1 ohne, in 9 mit Perfekt).
    formen = dict(eintrag.get("formen") or {})
    for andere in gruppe["entries"]:
        for k, v in (andere.get("formen") or {}).items():
            if v and not formen.get(k):
                formen[k] = v
    wortart = gruppe["wortart"]
    teile = []

    if wortart == "Verb":
        # Die Stammformen in der Reihenfolge, in der man sie lernt
        for k in ("praesens", "praesens_3sg", "praesens_3pl", "infinitiv", "perfekt", "ppp"):
            if formen.get(k):
                teile.append(formen[k])
    elif wortart == "Substantiv":
        if formen.get("nominativ"):
            teile.append(formen["nominativ"])
        if formen.get("genitiv"):
            teile.append("Gen. " + formen["genitiv"])
    elif wortart in ("Adjektiv", "Pronomen"):
        drei = [formen.get(k) for k in ("m", "f", "n")]
        if all(drei) and drei[0] == drei[1] == drei[2]:
            teile.append(drei[0])          # einendig: "potēns" statt dreimal
        else:
            teile += [x for x in drei if x]
        if not teile and formen.get("nominativ"):
            teile.append(formen["nominativ"])
        if formen.get("genitiv"):
            teile.append("Gen. " + formen["genitiv"])
    else:
        teile = [v for v in formen.values() if v]

    zusatz = []
    if eintrag.get("genus"):
        zusatz.append(eintrag["genus"])
    if eintrag.get("deklination"):
        zusatz.append(f"{eintrag['deklination']}. Deklination")
    if formen.get("genitiv_pl"):
        zusatz.append(f"Gen. Pl. {formen['genitiv_pl']}")
    if eintrag.get("numerus"):
        zusatz.append(f"nur {eintrag['numerus']}")
    if eintrag.get("kasus"):
        zusatz.append(f"m. {eintrag['kasus']}")
    if wortart == "Verb" and gruppe.get("conj"):
        zusatz.append(CONJ_NAMES[gruppe["conj"]])
    # Die Wortart selbst steht schon in der Kopfzeile der Frage - bei Adverbien
    # und Wendungen bleibt die Zeile deshalb einfach leer.

    kopf = ", ".join(teile)
    rest = "  ·  ".join(zusatz)
    if kopf and rest:
        return f"{kopf}  ·  {rest}"
    return kopf or rest


def pruefe_latein(antwort, gruppe, db):
    """Bewertet eine lateinische Antwort.  Liefert (Bewertung, Treffer, Form).

    Die Grundform zählt.  Eine erkannte gebeugte Form zählt auch, wird aber
    als solche gemeldet - dafür ist die Formenerkennung da."""
    erlaubt = set()
    for e in gruppe["entries"]:
        erlaubt |= latin_variants(e["latein"])
    if gruppe["wortart"] == "Verb" and gruppe.get("inf"):
        erlaubt |= latin_variants(gruppe["inf"])
    bestes, bester_treffer = FALSCH, None
    for teil in _teile(antwort):
        ok, treffer, exakt = _passt(norm(teil), erlaubt)
        if ok:
            if exakt:
                return PERFEKT, treffer, None
            bestes, bester_treffer = RICHTIG, treffer
    if bestes == RICHTIG:
        return bestes, bester_treffer, None
    # Keine Grundform - ist es wenigstens eine Form desselben Wortes?
    for teil in _teile(antwort):
        nt = norm(teil)
        labels = db.form_index.get(nt, {}).get(gruppe["id"])
        if labels:
            return RICHTIG, nt, labels[0]
    return FALSCH, None, None


# --------------------------------------------------------------------------
#  Auswahl der Vokabeln
# --------------------------------------------------------------------------

def lektionen_parsen(text, vorhanden):
    """1-8 / 3,5 / 12 / alle  ->  Menge von Lektionsnummern (None = ungueltig)."""
    text = text.strip().lower()
    if not text or text in ("alle", "all", "*"):
        return set(vorhanden)
    ergebnis = set()
    for stueck in text.replace(" ", "").split(","):
        if not stueck:
            continue
        if "-" in stueck:
            a, _, b = stueck.partition("-")
            try:
                von, bis = int(a), int(b)
            except ValueError:
                return None
            if von > bis:
                von, bis = bis, von
            ergebnis |= {n for n in vorhanden if von <= n <= bis}
        else:
            try:
                n = int(stueck)
            except ValueError:
                return None
            if n in vorhanden:
                ergebnis.add(n)
    return ergebnis or None


def gruppen_waehlen(db, lektionen, wortarten):
    """Alle Gruppen, die zur Lektions- und Wortartauswahl passen."""
    treffer = []
    for g in db.groups:
        if wortarten and g["wortart"] not in wortarten:
            continue
        passende = [e for e in g["entries"] if e["lektion"] in lektionen]
        if passende:
            treffer.append((g, passende[0]))
    return treffer


# --------------------------------------------------------------------------
#  Eingabehilfen
# --------------------------------------------------------------------------

def frage_auswahl(text, optionen, standard):
    """optionen: dict {eingabe: rueckgabe}.  None = abgebrochen."""
    while True:
        antwort = ask(text)
        if antwort is None:
            return None
        antwort = antwort.strip().lower() or standard
        if antwort in optionen:
            return optionen[antwort]
        emit("   Bitte eine der angebotenen Moeglichkeiten waehlen.")


def frage_zahl(text, standard, minimum=1, maximum=None, alle=None):
    """alle: Anzahl, die bei der Eingabe "alle" zurückgegeben wird."""
    while True:
        antwort = ask(text)
        if antwort is None:
            return None
        antwort = antwort.strip() or str(standard)
        if alle is not None and antwort.lower() in ("alle", "all", "a", "*"):
            return alle
        try:
            zahl = int(antwort)
        except ValueError:
            emit("   Bitte eine ganze Zahl oder \"alle\" eingeben.")
            continue
        if zahl < minimum:
            emit(f"   Bitte mindestens {minimum} eingeben.")
            continue
        if maximum is not None and zahl > maximum:
            emit(f"   Hoechstens {maximum} moeglich.")
            continue
        return zahl


# --------------------------------------------------------------------------
#  Fragerunden   (Rueckgabe: True/False, None = abgebrochen)
# --------------------------------------------------------------------------

def runde_bedeutung(db, gruppe, eintrag, richtung):
    """richtung 1: Latein -> Deutsch,  2: Deutsch -> Latein."""
    kopf = f"[Lektion {eintrag['lektion']}, {gruppe['wortart']}]"
    if richtung == 1:
        emit(f"\n   {eintrag['latein']}     {kopf}")
        antwort = ask("   Deutsch: ")
        if antwort is None:
            return None
        bewertung, _treffer = pruefe_deutsch(antwort, eintrag, db, gruppe)
        loesung, hinweis = eintrag["deutsch"], None
    else:
        emit(f"\n   {eintrag['deutsch']}     {kopf}")
        antwort = ask("   Latein: ")
        if antwort is None:
            return None
        bewertung, _treffer, form = pruefe_latein(antwort, gruppe, db)
        loesung = eintrag["latein"]
        hinweis = f"Das ist {form} - die Grundform heisst {loesung}." if form else None

    # Die vollstaendige Loesung kommt immer - auch bei richtiger Antwort, damit
    # man die uebrigen Bedeutungen und die Schreibweise mit Laengenzeichen sieht.
    emit(URTEIL[bewertung])
    emit(f"       Lösung: {loesung}")
    angaben = stammformen(gruppe, eintrag)
    if angaben:
        emit(f"       {angaben}")
    if hinweis:
        emit(f"       {hinweis}")
    return bewertung


# Formen, die mit einer anderen identisch sind - die fragt niemand ab.
RANDFORMEN = ("Vokativ Pl.",)

# In welcher Lektion das Lehrbuch die Form einführt.  99 heißt: kommt bis
# Lektion 20 nicht vor (Konjunktiv, Steigerung, Gerundium, Futur II ...).
# Die Reihenfolge zählt - geprüft wird der erste passende Anfang.
FORM_LEKTION = (
    ("Konjunktiv", 99), ("Gerundium", 99), ("Gerundivum", 99), ("PFA", 99),
    ("Supinum", 99), ("Infinitiv Futur", 99), ("Partizip Präsens", 99),
    ("Futur II", 99), ("Futur I Passiv", 99),
    ("Komparativ", 99), ("Superlativ", 99), ("Adverb", 99),
    ("Infinitiv Perfekt Passiv", 14), ("PPP", 14),
    ("Präsens Passiv", 13), ("Imperfekt Passiv", 13),
    ("Infinitiv Präsens Passiv", 13),
    ("Futur I", 11),
    ("Plusquamperfekt", 10),
    ("Imperfekt Aktiv", 8), ("Perfekt Aktiv", 8), ("Infinitiv Perfekt", 8),
    ("Präsens Aktiv", 1), ("Imperativ", 1), ("Infinitiv", 1), ("Präsens", 1),
)

KASUS_ANFANG = ("Nominativ", "Genitiv", "Dativ", "Akkusativ", "Ablativ", "Vokativ")

# Auswahl für „welche Grammatik?" im Formen-Quiz
FORM_BEREICHE = (
    ("alle Formen", None),
    ("Präsens", ("Präsens Aktiv",)),
    ("Imperfekt", ("Imperfekt Aktiv",)),
    ("Perfekt", ("Perfekt Aktiv",)),
    ("Plusquamperfekt", ("Plusquamperfekt",)),
    ("Futur", ("Futur",)),
    ("Passiv", ("Präsens Passiv", "Imperfekt Passiv", "Futur I Passiv",
                "Infinitiv Präsens Passiv", "Infinitiv Perfekt Passiv")),
    ("Konjunktiv", ("Konjunktiv",)),
    ("Imperativ und Infinitiv", ("Imperativ", "Infinitiv")),
    ("Partizipien (PPA, PPP, PFA)", ("Partizip Präsens", "PPP", "PFA")),
    ("Gerundium, Gerundivum, Supinum", ("Gerundium", "Gerundivum", "Supinum")),
    ("Deklination (Substantive, Adjektive)", KASUS_ANFANG),
    ("Steigerung und Adverb", ("Komparativ", "Superlativ", "Adverb")),
)

# Abfragearten im Formen-Quiz
ARTEN = (("gemischt", "gemischt"),
         ("bilden", "Form bilden"),
         ("bestimmen", "Grundform zur Form nennen"))


def form_lektion(label):
    """Lektion, in der diese Form im Lehrbuch eingeführt wird."""
    for anfang, lektion in FORM_LEKTION:
        if label.startswith(anfang):
            return lektion
    return 1          # Kasusformen und Pronomen laufen von Anfang an mit


def sauberes_label(label):
    """Klammerhinweise wie "[regelmaessig gebildet]" aus der Frage nehmen -
    aber nur die Klammer, nicht den Kasus, der dahinter steht."""
    return re.sub(r"\s*\[[^\]]*\]", "", label).strip()


def formen_zeilen(gruppe, bis_lektion=None, bereich=None):
    """Abfragbare Zeilen eines Paradigmas.

    bis_lektion  nur Formen, die das Buch bis zu dieser Lektion einführt
    bereich      Tupel von Anfängen, z. B. ("Perfekt Aktiv",) - None = alles
    """
    par = gruppe.get("par")
    if not par:
        return []
    zeilen = []
    for label, person, alts in par.rows:
        if "ungeprüft" in label or not alts or not alts[0]:
            continue
        sauber = sauberes_label(label)
        if any(r in sauber for r in RANDFORMEN):
            continue
        if bis_lektion is not None and form_lektion(sauber) > bis_lektion:
            continue
        if bereich and not any(sauber.startswith(a) for a in bereich):
            continue
        zeilen.append((sauber, person, alts))
    return zeilen


def runde_formen(db, gruppe, eintrag, bis_lektion=None, bereich=None, art="gemischt"):
    """Zwei Fragetypen: Form bilden bzw. Grundform zu einer Form nennen."""
    zeilen = formen_zeilen(gruppe, bis_lektion, bereich)
    if not zeilen:
        return None
    label, person, alts = random.choice(zeilen)
    bestimmung = label + (", " + person if person else "")

    bilden = art == "bilden" or (art == "gemischt" and random.random() < 0.5)
    if bilden:
        emit(f"\n   {gruppe['lemma']}   ({eintrag['deutsch']})")
        emit(f"   Gesucht: {bestimmung}")
        antwort = ask("   Form: ")
        if antwort is None:
            return None
        erlaubt = {norm(a) for a in alts if norm(a)}
        ok, _treffer, exakt = _passt(norm(antwort), erlaubt)
        bewertung = PERFEKT if exakt else RICHTIG if ok else FALSCH
        loesung = " / ".join(alts)
    else:
        emit(f"\n   {alts[0]}")
        antwort = ask("   Von welcher Vokabel stammt diese Form? ")
        if antwort is None:
            return None
        bewertung, _treffer, _form = pruefe_latein(antwort, gruppe, db)
        loesung = f"{gruppe['lemma']}   ({bestimmung})  –  {eintrag['deutsch']}"

    emit(URTEIL[bewertung])
    emit(f"       Lösung: {loesung}")
    angaben = stammformen(gruppe, eintrag)
    if angaben:
        emit(f"       {angaben}")
    return bewertung


# --------------------------------------------------------------------------
#  Quiz
# --------------------------------------------------------------------------

def einstellungen(db, fehler):
    """Fragt Auswahl und Modus ab.  None = abgebrochen."""
    nur_fehler = False
    offen = fehler.zahlen()["offen"]
    if offen:
        nur_fehler = frage_auswahl(
            f"\nWas üben? [1] alle Vokabeln  [2] nur meine {offen} Fehlervokabeln [1]: ",
            {"1": False, "2": True}, "1")
        if nur_fehler is None:
            return None

    vorhanden = sorted({e["lektion"] for e in db.entries})
    lektionen, wortarten = set(vorhanden), None
    if not nur_fehler:
        emit(f"\nLektionen {vorhanden[0]}-{vorhanden[-1]} sind vorhanden.")
    while not nur_fehler:
        antwort = ask("Welche Lektionen? (z. B. 1-8, 3,5 oder alle) [alle]: ")
        if antwort is None:
            return None
        gewaehlt = lektionen_parsen(antwort, vorhanden)
        if gewaehlt:
            lektionen = gewaehlt
            break
        emit("   Das konnte ich nicht lesen.  Beispiele:  1-8   3,5   alle")

    arten = [w for w in WORTART_ORDER if any(g["wortart"] == w for g in db.groups)]
    if not nur_fehler:
        emit("\nWortarten:  0 = alle,  "
             + ",  ".join(f"{i + 1} = {w}" for i, w in enumerate(arten)))
    while not nur_fehler:
        antwort = ask("Welche Wortarten? (Nummern, z. B. 1,2) [0]: ")
        if antwort is None:
            return None
        antwort = antwort.strip() or "0"
        if antwort == "0":
            wortarten = None
            break
        try:
            nummern = [int(x) for x in antwort.replace(" ", "").split(",") if x]
        except ValueError:
            emit("   Bitte Nummern eingeben.")
            continue
        if nummern and all(1 <= n <= len(arten) for n in nummern):
            wortarten = {arten[n - 1] for n in nummern}
            break
        emit(f"   Bitte Nummern zwischen 1 und {len(arten)}.")

    modus = frage_auswahl(
        "\nModus: [1] Latein->Deutsch  [2] Deutsch->Latein  [3] gemischt  [4] Formen-Quiz [1]: ",
        {"1": "ld", "2": "dl", "3": "mix", "4": "formen"}, "1")
    if modus is None:
        return None

    bis_lektion, bereich, art = None, None, "gemischt"
    if modus == "formen":
        hoechste = max(lektionen)
        wahl = frage_auswahl(
            f"\nWelche Formen? [1] nur bis Lektion {hoechste}  [2] bis Lektion … "
            f"[3] alle (auch Konjunktiv, Steigerung …) [1]: ",
            {"1": "auswahl", "2": "eigene", "3": "alle"}, "1")
        if wahl is None:
            return None
        if wahl == "auswahl":
            bis_lektion = hoechste
        elif wahl == "eigene":
            bis_lektion = frage_zahl("   Bis zu welcher Lektion? [14]: ", 14, 1, 99)
            if bis_lektion is None:
                return None

        emit("\nWelche Grammatik?")
        for i, (name, _p) in enumerate(FORM_BEREICHE, 1):
            emit(f"   [{i}] {name}")
        nummer = frage_zahl("Auswahl [1]: ", 1, 1, len(FORM_BEREICHE))
        if nummer is None:
            return None
        bereich = FORM_BEREICHE[nummer - 1][1]

        art = frage_auswahl(
            "\nAbfrageart: [1] gemischt  [2] Form bilden  "
            "[3] Grundform zur Form nennen [1]: ",
            {"1": "gemischt", "2": "bilden", "3": "bestimmen"}, "1")
        if art is None:
            return None
    return lektionen, wortarten, modus, (bis_lektion, bereich, art), nur_fehler


def start_quiz(db=None):
    """Startet das Quiz.  db kann von aussen mitgegeben werden (Befehl :quiz)."""
    setup_console()
    if db is None:
        db = VokabelBase()

    fehler = FD.FehlerListe()
    statistik = FD.Statistik()
    for warnung in (fehler.warnung, statistik.warnung):
        if warnung:
            emit(warnung)

    emit("=== Vokabelquiz ===")
    emit("Abbrechen jederzeit mit Strg+C.")
    emit(statistik.kurzfassung())

    while True:
        wahl = einstellungen(db, fehler)
        if wahl is None:
            emit("\nAbgebrochen.")
            return
        lektionen, wortarten, modus, formen_wahl, nur_fehler = wahl
        bis_lektion, bereich, art = formen_wahl

        paare = fehler.paare(db) if nur_fehler else gruppen_waehlen(db, lektionen, wortarten)
        if modus == "formen":
            paare = [(g, e) for g, e in paare
                     if formen_zeilen(g, bis_lektion, bereich)]
        if not paare:
            emit("\nZu dieser Auswahl gibt es keine Vokabeln.  Bitte anders waehlen.")
            continue

        emit(f"\n{len(paare)} Vokabeln stehen zur Auswahl.")
        anzahl = frage_zahl(f"Wie viele Fragen? (Zahl oder \"alle\") [10]: ",
                            10, 1, 2000, alle=len(paare))
        if anzahl is None:
            emit("\nAbgebrochen.")
            return

        # Ohne Wiederholung, solange der Vorrat reicht
        if anzahl <= len(paare):
            aufgaben = random.sample(paare, anzahl)
        else:
            aufgaben = random.choices(paare, k=anzahl)

        zaehler = {PERFEKT: 0, RICHTIG: 0, FALSCH: 0}
        falsche, gestellt = [], 0
        for gruppe, eintrag in aufgaben:
            if modus == "formen":
                ergebnis = runde_formen(db, gruppe, eintrag, bis_lektion, bereich, art)
            else:
                richtung = 1 if modus == "ld" else 2 if modus == "dl" else random.choice((1, 2))
                ergebnis = runde_bedeutung(db, gruppe, eintrag, richtung)
            if ergebnis is None:          # Strg+C mitten im Quiz
                emit("\nQuiz abgebrochen.")
                break
            gestellt += 1
            zaehler[ergebnis] += 1
            statistik.buchen(gruppe, eintrag, ergebnis)
            if ergebnis == FALSCH:
                falsche.append(eintrag)
                v = fehler.falsch(gruppe, eintrag)
                emit(f"       Fehlerliste: {fehler.fortschritt(v)}   "
                     f"({v['falsch']}× falsch)")
            else:
                v, geschafft = fehler.richtig(gruppe, eintrag)
                if geschafft:
                    emit("       Geschafft – raus aus der Fehlerliste!")
                elif v:
                    emit(f"       Fehlerliste: {fehler.fortschritt(v)}   "
                         f"noch {FD.ZIEL_PUNKTE - v['punkte']}× richtig")

        if gestellt:
            gut = zaehler[PERFEKT] + zaehler[RICHTIG]
            prozent = round(100 * gut / gestellt)
            emit(f"\n-- Ergebnis: {gut}/{gestellt} richtig ({prozent} %) --")
            emit(f"   {zaehler[PERFEKT]}× perfekt  ·  {zaehler[RICHTIG]}× richtig  ·  "
                 f"{zaehler[FALSCH]}× falsch")
            offen = fehler.zahlen()["offen"]
            emit(f"   Fehlerliste: {offen} Vokabeln in Übung")
            emit(f"   Insgesamt {statistik.kurzfassung()}")
        if falsche:
            emit("\nDas solltest du dir nochmal ansehen:")
            for eintrag in falsche:
                emit(f"    {eintrag['latein']:<28} {eintrag['deutsch']}")

        nochmal = frage_auswahl("\nNochmal? [j/n] [n]: ",
                                {**{k: True for k in JA}, **{k: False for k in NEIN}}, "n")
        if not nochmal:
            break
    emit("Bis bald!")


if __name__ == "__main__":
    try:
        start_quiz()
    except KeyboardInterrupt:
        emit("\nAbgebrochen.")
        sys.exit(0)
