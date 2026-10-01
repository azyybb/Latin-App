"""
grammatik.py  -  erzeugt Grammatiktabellen aus der Vokabeldatenbank
===================================================================
Die Tabellen werden nicht abgetippt, sondern aus denselben Formen gebaut,
die auch die Suche benutzt.  Damit stimmen sie automatisch mit dem
Vokabelbestand ueberein.

  tafeln_lektion(db, 9)          alles, was in Lektion 9 neu dazukommt
  tafeln_zeit(db, "Perfekt Aktiv")   eine Zeit, alle Konjugationen nebeneinander
  tafeln_konjugationen(db)       je Konjugation eine vollstaendige Tabelle
  tafeln_unregelmaessig(db)      esse, posse, ire, velle, nolle, ferre
  tafeln_deklinationen(db)       1. bis 5. Deklination
  tafeln_pronomen(db)            is, hic, ille, iste, idem, qui
  tafeln_steigerung(db)          Komparativ und Superlativ
"""

import re

import pfade
from bettervokable_search import CASES, CONJ_NAMES, PERS, norm

BILDER_ORDNER = pfade.GRAMMATIK_BILDER


def buchseiten(lektion):
    """Die abfotografierten Buchseiten dieser Lektion, in Buchreihenfolge."""
    if not BILDER_ORDNER.is_dir():
        return []
    return sorted(BILDER_ORDNER.glob(f"lektion{lektion:02d}_*.jpg"),
                  key=lambda p: (len(p.stem), p.stem))


def lektionen_mit_seiten():
    """{Lektion: Anzahl Seiten} - fuer die Themenliste."""
    if not BILDER_ORDNER.is_dir():
        return {}
    gefunden = {}
    for p in BILDER_ORDNER.glob("lektion*_*.jpg"):
        ziffern = p.stem[len("lektion"):].split("_")[0]
        if ziffern.isdigit():
            gefunden[int(ziffern)] = gefunden.get(int(ziffern), 0) + 1
    return gefunden

KONJ_KURZ = {"A": "a-Konj.", "E": "e-Konj.", "I": "i-Konj.",
             "C": "kons. Konj.", "CAP": "capere-Typ"}
KONJ_REIHE = ["A", "E", "I", "C", "CAP"]
UNREGELMAESSIG = ["ESSE", "POSSE", "IRE", "VELLE", "NOLLE", "FERRE"]

ZEITEN = [
    "Präsens Aktiv", "Imperfekt Aktiv", "Futur I Aktiv",
    "Perfekt Aktiv", "Plusquamperfekt Aktiv", "Futur II Aktiv",
    "Präsens Passiv", "Imperfekt Passiv", "Futur I Passiv",
    "Konjunktiv Präsens Aktiv", "Konjunktiv Imperfekt Aktiv",
    "Konjunktiv Perfekt Aktiv", "Konjunktiv Plusquamperfekt Aktiv",
    "Konjunktiv Präsens Passiv", "Konjunktiv Imperfekt Passiv",
]

_KLAMMER = re.compile(r"\s*\[[^\]]*\]")


def _sauber(label):
    return _KLAMMER.sub("", label).strip()


# --------------------------------------------------------------------------
#  Tafel
# --------------------------------------------------------------------------

class Tafel:
    """Eine Tabelle: Titel, Spaltenkoepfe und Zeilen."""

    def __init__(self, titel, kopf, zeilen, hinweis=""):
        self.titel = titel
        self.kopf = kopf
        self.zeilen = [z for z in zeilen if any(x for x in z[1:])]
        self.hinweis = hinweis

    def leer(self):
        return not self.zeilen

    def text(self):
        spalten = len(self.kopf)
        breiten = []
        for i in range(spalten):
            inhalt = [self.kopf[i]] + [str(z[i]) if i < len(z) else "" for z in self.zeilen]
            breiten.append(max(len(x) for x in inhalt))
        zeilen = [self.titel, "─" * max(len(self.titel), sum(breiten) + 3 * (spalten - 1))]
        if any(self.kopf[1:]):
            zeilen.append("   ".join(k.ljust(b) for k, b in zip(self.kopf, breiten)).rstrip())
            zeilen.append("   ".join("─" * b for b in breiten).rstrip())
        for z in self.zeilen:
            felder = [str(z[i]) if i < len(z) else "" for i in range(spalten)]
            zeilen.append("   ".join(f.ljust(b) for f, b in zip(felder, breiten)).rstrip())
        if self.hinweis:
            zeilen.append("")
            zeilen.append(self.hinweis)
        return "\n".join(zeilen)


# --------------------------------------------------------------------------
#  Zugriff auf die erzeugten Formen
# --------------------------------------------------------------------------

def _index(gruppe):
    """(sauberes Label, Person) -> Liste der Formen."""
    par = gruppe.get("par")
    if not par:
        return {}
    d = {}
    for label, person, alts in par.rows:
        k = (_sauber(label), person)
        ziel = d.setdefault(k, [])
        for a in alts:
            if a and a not in ziel:
                ziel.append(a)
    return d


def _form(index, label, person=None):
    return " / ".join(index.get((label, person), []))


def zitierform(gruppe):
    """Lemma mit Laengenzeichen, so wie es im Buch steht."""
    e = gruppe["entries"][0]
    formen = e.get("formen") or {}
    for k in ("infinitiv", "nominativ", "m"):
        if formen.get(k):
            return formen[k]
    return gruppe["lemma"]


def _gruppe(db, lemma):
    for g in db.groups:
        if g["lemma"] == lemma:
            return g
    return None


# Die Verben, an denen das Lehrbuch die Konjugationen vorführt
MUSTER_BUCH = {"A": "vocare", "E": "monere", "I": "audire",
               "C": "ducere", "CAP": "capere"}


def musterverb(db, conj, mit_perfekt=False):
    """Ein moeglichst typisches Verb dieser Konjugation.
    mit_perfekt: bevorzugt eines, dessen Perfekt im Buch steht."""
    treffer = [g for g in db.groups if g["wortart"] == "Verb" and g.get("conj") == conj]
    if not treffer:
        return None
    # Erst das Vorbild des Lehrbuchs, damit die Tabellen wiedererkennbar sind
    vorbild = _gruppe(db, MUSTER_BUCH.get(conj, ""))
    if vorbild in treffer:
        return vorbild
    if mit_perfekt:
        sicher = [g for g in treffer if g.get("pf_src") == "buch" and g.get("ppp_stem")]
        if sicher:
            treffer = sicher
        else:
            sicher = [g for g in treffer if g.get("pf_src") == "buch"]
            if sicher:
                treffer = sicher
    treffer.sort(key=lambda g: (g["entries"][0]["lektion"], norm(g["lemma"])))
    return treffer[0]


def mustersubstantiv(db, deklination, genus):
    treffer = [g for g in db.groups
               if g["wortart"] == "Substantiv"
               and g["entries"][0].get("deklination") == deklination
               and g["entries"][0].get("genus") == genus
               and g["entries"][0].get("numerus") != "Pl"
               and " " not in g["lemma"]]
    treffer.sort(key=lambda g: (g["entries"][0]["lektion"], norm(g["lemma"])))
    return treffer[0] if treffer else None


# --------------------------------------------------------------------------
#  Verben
# --------------------------------------------------------------------------

def tafel_verb_zeit(gruppe, zeit):
    """Eine Zeit eines Verbs, sechs Personen untereinander."""
    index = _index(gruppe)
    zeilen = [(p, _form(index, zeit, p)) for p in PERS]
    return Tafel(f"{gruppe['lemma']} – {zeit}", ["", ""], zeilen)


def tafel_zeit_alle(db, zeit):
    """Eine Zeit, alle Konjugationen nebeneinander."""
    braucht_perfekt = any(w in zeit for w in ("Perfekt", "Plusquamperfekt", "Futur II"))
    verben, kopf = [], [""]
    for conj in KONJ_REIHE:
        g = musterverb(db, conj, mit_perfekt=braucht_perfekt)
        if g:
            verben.append(g)
            kopf.append(f"{KONJ_KURZ[conj]} ({g['lemma']})")
    zeilen = []
    for p in PERS:
        zeile = [p] + [_form(_index(g), zeit, p) for g in verben]
        zeilen.append(zeile)
    hinweis = ("Die Formen stammen aus den Stammformen der Vokabeldatei; wo das Buch "
               "keinen Perfektstamm angibt, fehlt die Spalte." if braucht_perfekt else "")
    return Tafel(f"{zeit} – alle Konjugationen", kopf, zeilen, hinweis)


def tafeln_verb_formen(gruppe, zeiten, zusatz=True):
    """Ausgewaehlte Zeiten eines Verbs nebeneinander - so viel wie das Buch an
    dieser Stelle zeigt, nicht das ganze Paradigma."""
    index = _index(gruppe)
    vorhanden = [z for z in zeiten if _form(index, z, PERS[0])]
    if not vorhanden:
        return []
    zeilen = [[p] + [_form(index, z, p) for z in vorhanden] for p in PERS]
    tafeln = [Tafel(f"{zitierform(gruppe)} – {', '.join(vorhanden)}",
                    [""] + vorhanden, zeilen)]
    if not zusatz:
        return tafeln
    rest = []
    for label, name in (("Infinitiv Präsens Aktiv", "Infinitiv Präsens"),
                        ("Infinitiv Präsens", "Infinitiv Präsens"),
                        ("Infinitiv Perfekt Aktiv", "Infinitiv Perfekt"),
                        ("Infinitiv Perfekt", "Infinitiv Perfekt")):
        wert = _form(index, label)
        if wert and not any(n == name for n, _w in rest):
            rest.append((name, wert))
    for p, name in (("2. Pers. Sg.", "Imperativ Sg."), ("2. Pers. Pl.", "Imperativ Pl.")):
        wert = _form(index, "Imperativ Aktiv", p)
        if wert:
            rest.append((name, wert))
    if rest:
        tafeln.append(Tafel("Infinitiv und Imperativ", ["", ""], rest))
    return tafeln


def tafeln_verb_vollstaendig(gruppe):
    """Alle Zeiten eines Verbs, je eine kleine Tabelle."""
    index = _index(gruppe)
    vorhanden = []
    for label, person in index:
        if label not in vorhanden and any(label == z for z in ZEITEN):
            vorhanden.append(label)
    vorhanden.sort(key=ZEITEN.index)
    tafeln = []
    for zeit in vorhanden:
        tafeln.append(Tafel(zeit, ["", ""], [(p, _form(index, zeit, p)) for p in PERS]))
    # Infinitive und Imperativ als eine kleine Tabelle dazu
    rest = []
    for label in ("Infinitiv Präsens Aktiv", "Infinitiv Präsens Passiv",
                  "Infinitiv Perfekt Aktiv", "Infinitiv Präsens", "Infinitiv Perfekt",
                  "Infinitiv"):
        wert = _form(index, label)
        if wert:
            rest.append((label, wert))
    for p in ("2. Pers. Sg.", "2. Pers. Pl."):
        wert = _form(index, "Imperativ Aktiv", p)
        if wert:
            rest.append((f"Imperativ {p}", wert))
    for label in ("PPP Nominativ Sg. m", "PFA Nominativ Sg. m",
                  "Partizip Präsens (PPA) Nominativ Sg. m"):
        wert = _form(index, label)
        if wert:
            rest.append((label.replace(" Nominativ Sg. m", ""), wert))
    if rest:
        tafeln.append(Tafel("Infinitive, Imperativ, Partizipien", ["", ""], rest))
    return tafeln


def tafeln_konjugationen(db):
    tafeln = []
    for conj in KONJ_REIHE:
        g = musterverb(db, conj, mit_perfekt=True)
        if not g:
            continue
        index = _index(g)
        zeilen = []
        for zeit in ZEITEN:
            if _form(index, zeit, PERS[0]):
                zeilen.append((zeit, _form(index, zeit, PERS[0]),
                               _form(index, zeit, PERS[2]),
                               _form(index, zeit, PERS[5])))
        tafeln.append(Tafel(f"{CONJ_NAMES[conj]} – Muster: {zitierform(g)}",
                            ["", "1. Sg.", "3. Sg.", "3. Pl."], zeilen))
    return tafeln


def tafeln_unregelmaessig(db):
    """Je Vorbild eine Tabelle mit den vier wichtigsten Zeiten nebeneinander."""
    tafeln = []
    for conj in UNREGELMAESSIG:
        gruppe = next((g for g in db.groups
                       if g["wortart"] == "Verb" and g.get("conj") == conj), None)
        if not gruppe:
            continue
        index = _index(gruppe)
        zeiten = [z for z in ZEITEN if _form(index, z, PERS[0])][:4]
        if not zeiten:
            continue
        zeilen = [[p] + [_form(index, z, p) for z in zeiten] for p in PERS]
        tafeln.append(Tafel(f"{zitierform(gruppe)} – {CONJ_NAMES[conj]}",
                            [""] + zeiten, zeilen))
    return [t for t in tafeln if not t.leer()]


def _zeilen_mehrzeit(gruppe, zeiten):
    index = _index(gruppe)
    return [[p] + [_form(index, z, p) for z in zeiten] for p in PERS]


# --------------------------------------------------------------------------
#  Substantive, Adjektive, Pronomen
# --------------------------------------------------------------------------

def tafel_substantiv(gruppe):
    index = _index(gruppe)
    e = gruppe["entries"][0]
    zeilen = []
    for kasus in CASES:
        zeilen.append((kasus, _form(index, f"{kasus} Sg."), _form(index, f"{kasus} Pl.")))
    titel = (f"{zitierform(gruppe)} – {e.get('deklination')}. Deklination "
             f"({e.get('genus')})")
    return Tafel(titel, ["", "Singular", "Plural"], zeilen)


def tafeln_deklinationen(db):
    tafeln = []
    gesehen = set()
    for dekl in (1, 2, 3, 4, 5):
        for genus in ("m", "f", "n"):
            g = mustersubstantiv(db, dekl, genus)
            if g and g["id"] not in gesehen:
                gesehen.add(g["id"])
                t = tafel_substantiv(g)
                if not t.leer():
                    tafeln.append(t)
    return tafeln


def tafel_adjektiv(gruppe):
    index = _index(gruppe)
    zeilen = []
    for kasus in CASES:
        for num in ("Sg.", "Pl."):
            werte = [_form(index, f"{kasus} {num} {g}") for g in ("m", "f", "n")]
            if any(werte):
                zeilen.append([f"{kasus} {num}"] + werte)
    return Tafel(f"{zitierform(gruppe)} – Adjektiv", ["", "m", "f", "n"], zeilen)


def tafeln_pronomen(db):
    tafeln = []
    for lemma in ("is, ea, id", "hic, haec, hoc", "ille, illa, illud",
                  "iste, ista, istud", "idem, eadem, idem", "qui, quae, quod"):
        g = _gruppe(db, lemma)
        if not g:
            continue
        index = _index(g)
        zeilen = [(label, " / ".join(formen))
                  for (label, _p), formen in index.items()
                  if formen and label not in ("m", "f", "n")]
        if zeilen:
            tafeln.append(Tafel(f"{lemma}", ["", ""], zeilen))
    return tafeln


def tafeln_steigerung(db):
    tafeln = []
    for lemma in ("altus", "fortis", "bonus", "magnus", "malus", "parvus", "multus"):
        g = _gruppe(db, lemma)
        if not g:
            continue
        index = _index(g)
        zeilen = [
            ("Positiv", _form(index, "Nominativ Sg. m"), _form(index, "Nominativ Sg. f"),
             _form(index, "Nominativ Sg. n")),
            ("Komparativ", _form(index, "Komparativ Nominativ Sg. m"),
             _form(index, "Komparativ Nominativ Sg. f"),
             _form(index, "Komparativ Nominativ Sg. n")),
            ("Superlativ", _form(index, "Superlativ Nominativ Sg. m"),
             _form(index, "Superlativ Nominativ Sg. f"),
             _form(index, "Superlativ Nominativ Sg. n")),
            ("Adverb", _form(index, "Adverb"), _form(index, "Adverb Komparativ"),
             _form(index, "Adverb Superlativ")),
        ]
        t = Tafel(f"{zitierform(g)} – Steigerung", ["", "m", "f", "n"], zeilen,
                  "Die letzte Zeile zeigt das Adverb: Positiv · Komparativ · Superlativ.")
        if not t.leer():
            tafeln.append(t)
    return tafeln


# --------------------------------------------------------------------------
#  Nach Lektion
# --------------------------------------------------------------------------

class Merksatz:
    """Ein Regelblock ohne Tabelle - fuer Themen wie KNG-Kongruenz oder AcI.
    Hat dieselbe Schnittstelle wie Tafel, damit die Oberflaeche beides gleich
    behandeln kann."""

    def __init__(self, titel, regeln, beispiele=()):
        self.titel = titel
        self.regeln = [r for r in regeln if r]
        self.beispiele = list(beispiele)

    def leer(self):
        return not self.regeln and not self.beispiele

    def text(self):
        zeilen = [self.titel, "─" * max(len(self.titel), 40)]
        for r in self.regeln:
            zeilen.append("• " + r)
        if self.beispiele:
            zeilen.append("")
            for lat, deu in self.beispiele:
                zeilen.append("    " + lat)
                zeilen.append("    " + deu)
                zeilen.append("")
        return "\n".join(zeilen).rstrip()


# --------------------------------------------------------------------------
#  Zusammengesetzte Passivformen (PPP + esse)
# --------------------------------------------------------------------------

ESSE_HILFE = {
    "Perfekt": ["sum", "es", "est", "sumus", "estis", "sunt"],
    "Plusquamperfekt": ["eram", "eras", "erat", "eramus", "eratis", "erant"],
}


def tafel_passiv_zusammengesetzt(gruppe, zeit):
    """z. B. vocatus, a, um sum  -  ich bin gerufen worden."""
    stamm = gruppe.get("ppp_stem")
    if not stamm:
        return Tafel("", ["", ""], [])
    hilfe = ESSE_HILFE[zeit]
    zeilen = []
    for i, person in enumerate(PERS):
        if i < 3:
            form = f"{stamm}us, a, um {hilfe[i]}"
        else:
            form = f"{stamm}i, ae, a {hilfe[i]}"
        zeilen.append((person, form))
    hinweis = (f"Die Passivformen des {zeit}s bestehen aus dem PPP "
               f"({stamm}us) und den "
               f"{'Präsens' if zeit == 'Perfekt' else 'Imperfekt'}formen von esse.")
    return Tafel(f"{zitierform(gruppe)} – Passiv ({zeit})", ["", ""], zeilen, hinweis)


# --------------------------------------------------------------------------
#  Lehrplan: welche Grammatik steht auf welcher Buchseite
# --------------------------------------------------------------------------
#  Die Eintraege folgen den abfotografierten Grammatikseiten, damit die
#  erzeugten Tabellen dieselben Themen behandeln wie das Buch.

LEHRPLAN = {
    5: [
        ("subst", "serva"), ("subst", "servus"),
        ("merk", ("Genitiv als Attribut",
                  ["Der Genitiv ist meist Attribut (Beifügung), also Teil eines "
                   "Satzglieds.",
                   "Er bezeichnet oft die Zugehörigkeit oder den Besitzer.",
                   "Wir fragen: „Wessen?“"],
                  [("Tabernam amīcī videō.", "Ich sehe den Laden des Freundes."),
                   ("Turbam servōrum videō.", "Ich sehe eine Menge Sklaven.")])),
        ("verb_zeiten", ("scribere", ["Präsens Aktiv"])),
        ("subst", "consilium"),
    ],
    6: [
        ("adj", "magnus"),
        ("merk", ("Adjektive: KNG-Kongruenz",
                  ["Das Adjektiv richtet sich in Kasus, Numerus und Genus nach dem "
                   "Substantiv, zu dem es gehört.",
                   "Es steht meist hinter dem Substantiv; bei Mengen- und Zahlangaben "
                   "(magnus, multī) oft davor."],
                  [("Dominus bonus servīs prōvidet.", "Ein guter Herr sorgt für die Sklaven."),
                   ("Iuppiter multa sacra pōstulat.", "Jupiter verlangt viele Opfer.")])),
        ("merk", ("Adjektiv als Attribut und als Prädikatsnomen",
                  ["Als Attribut ist das Adjektiv Teil eines Satzglieds.",
                   "Als Prädikatsnomen tritt es mit esse zum Bezugswort."],
                  [("Dominus bonus servīs prōvidet.", "Ein guter Herr sorgt für die Sklaven."),
                   ("Superbia Promētheī magna est.", "Der Stolz des Prometheus ist groß.")])),
        ("merk", ("Wort- und Satzfragen",
                  ["Wortfragen beginnen mit einem Fragewort (quis, ubi, cūr …).",
                   "Satzfragen beginnen mit einer Fragepartikel: -ne lässt die Antwort "
                   "offen, nōnne erwartet „ja“, num erwartet „nein“."],
                  [("Quis venit?", "Wer kommt?"),
                   ("Venitne?", "Kommt er?"),
                   ("Nōnne venit?", "Kommt er (etwa) nicht?"),
                   ("Num venit?", "Kommt er etwa?")])),
        ("verb_zeiten", ("capere", ["Präsens Aktiv"])),
        ("subst", "puer"), ("adj", "miser"),
    ],
    7: [
        ("subst", "labor"), ("subst", "libertas"),
        ("verb_zeiten", ("posse", ["Präsens Aktiv"])),
        ("merk", ("Verben: Komposita",
                  ["Komposita bestehen aus einem einfachen Verb und einer Vorsilbe "
                   "(Präfix).",
                   "Da das Präfix oft als Präposition bekannt ist, lässt sich die "
                   "Bedeutung meist erschließen."],
                  [("ad-esse", "da sein, helfen"),
                   ("ab-esse", "abwesend sein, entfernt sein, fehlen"),
                   ("dē-esse", "fehlen")])),
    ],
    8: [
        ("zeit", "Imperfekt Aktiv"),
        ("verb_zeit", ("esse", "Imperfekt Aktiv")),
        ("zeit", "Perfekt Aktiv"),
        ("verb_zeit", ("esse", "Perfekt Aktiv")),
    ],
    9: [
        ("merk", ("AcI: Erweiterungen",
                  ["Der AcI kann durch Adverbialien oder Objekte erweitert werden.",
                   "Akkusativ und Infinitiv rahmen diese Ergänzungen in der Regel ein.",
                   "Ein Prädikatsnomen steht in KNG-Kongruenz zum Akkusativ des AcI."],
                  [("Claudia amīcum diū legere scit.",
                    "Claudia weiß, dass der Freund lange liest."),
                   ("Claudiam pulchram esse scīmus.",
                    "Wir wissen, dass Claudia schön ist.")])),
        ("merk", ("AcI: Zeitverhältnisse",
                  ["Der Infinitiv Präsens bezeichnet Gleichzeitigkeit.",
                   "Der Infinitiv Perfekt bezeichnet Vorzeitigkeit."],
                  [("Claudia amīcum dubitāre scit.",
                    "Claudia weiß, dass der Freund zweifelt."),
                   ("Claudia amīcum dubitāvisse scit.",
                    "Claudia weiß, dass der Freund gezweifelt hat.")])),
        ("stammformen", ("Verben: Perfekt (-s-, Dehnung, Reduplikation, ohne "
                         "Stammveränderung)",
                         ["manere", "dicere", "sentire", "videre", "cadere",
                          "parere", "animadvertere"])),
        ("subst", "homo"), ("subst", "pater"), ("subst", "pars"),
        ("merk", ("Personalpronomen",
                  ["Im Nominativ steht das Personalpronomen nur, wenn das Subjekt "
                   "besonders betont wird.",
                   "Mit cum verschmilzt der Ablativ: mēcum, tēcum, nōbīscum, vōbīscum."],
                  [("Ego dominus sum, tū servus es.",
                    "Ich bin der Herr, du bist der Sklave.")])),
    ],
    10: [
        ("pron", "is, ea, id"),
        ("merk", ("Pronomen is: Verwendung",
                  ["is wird oft als Demonstrativpronomen (hinweisendes Fürwort) "
                   "verwendet.",
                   "Es kommt auch als Personalpronomen anstelle einer bereits "
                   "genannten Person oder Sache vor.",
                   "Im Genitiv stehen die Formen meist als Possessivpronomen."],
                  [("is gladiātor", "dieser Gladiator"),
                   ("Ubi est gladiātor? Quis eum videt?",
                    "Wo ist der Gladiator? Wer sieht ihn?"),
                   ("Populus gladium eius videt.",
                    "Das Volk sieht sein (dessen) Schwert.")])),
        ("zeit", "Plusquamperfekt Aktiv"),
        ("merk", ("Verwendung des Plusquamperfekts",
                  ["Das Plusquamperfekt bezeichnet ein Ereignis der Vergangenheit, "
                   "das vor einem anderen vergangenen Ereignis liegt "
                   "(Vorvergangenheit).",
                   "Im Deutschen steht ebenfalls das Plusquamperfekt."],
                  [("Pater amīcōs monuerat; itaque urbem relīquērunt.",
                    "Der Vater hatte die Freunde gemahnt; deshalb verließen sie die "
                    "Stadt.")])),
        ("merk", ("Ablativ der Zeit",
                  ["Zeitangaben auf die Frage „wann?“ stehen im bloßen Ablativ "
                   "(Ablativus temporis).",
                   "Im Satz haben sie die Funktion des Adverbiales."],
                  [("eō annō", "in diesem Jahr"),
                   ("meā memoriā", "zu meiner Zeit"),
                   ("nocte", "in der Nacht, nachts")])),
    ],
    11: [
        ("pron", "qui, quae, quod"),
        ("merk", ("Relativsatz als Attribut",
                  ["Das Relativpronomen richtet sich in Numerus und Genus nach seinem "
                   "Bezugswort.",
                   "Der Kasus wird durch die Konstruktion des Relativsatzes "
                   "festgelegt.",
                   "Relativsätze haben die Funktion des Attributs."],
                  [("Cōgnōscimus frātrēs, quī urbem Rōmam cōnstituērunt.",
                    "Wir lernen die Brüder kennen, die die Stadt Rom gegründet haben."),
                   ("Rōmulus, cui cūnctī pārēbant, rēx Rōmānōrum erat.",
                    "Romulus, dem alle gehorchten, war König der Römer.")])),
        ("zeit", "Futur I Aktiv"),
        ("verb_zeit", ("esse", "Futur I Aktiv")),
        ("merk", ("Verwendung des Futurs",
                  ["Das Futur bezeichnet ein künftiges Geschehen.",
                   "Wo das Lateinische das Futur setzt, steht im Deutschen mit einem "
                   "Zeitadverb oft das Präsens."],
                  [("Mox in pāce vīvam et gaudēbō.",
                    "Bald werde ich in Frieden leben und mich freuen.")])),
    ],
    12: [
        ("adj", "acer"), ("adj", "fortis"), ("adj", "ingens"),
        ("merk", ("Reflexivpronomen (rückbezügliches Fürwort)",
                  ["Das Reflexivpronomen bezieht sich auf das Subjekt des Satzes.",
                   "Es ist im Akkusativ (sē), Dativ (sibi) und Ablativ (sē-cum) "
                   "wichtig; Singular und Plural werden nicht unterschieden.",
                   "Im Deutschen passt meist eine Übersetzung mit „sich“."],
                  [("Amīcae semper sē laudant.",
                    "Die Freundinnen loben immer sich."),
                   ("Servī sibi cibum parant.",
                    "Die Sklaven bereiten sich das Essen."),
                   ("Gladiātōrēs gladiōs sēcum habent.",
                    "Die Gladiatoren haben Schwerter bei sich.")])),
        ("merk", ("AcI: Pronomina",
                  ["Im AcI bezieht sich sē auf das Subjekt des übergeordneten Satzes.",
                   "Die Formen von is beziehen sich dagegen auf andere Personen "
                   "oder Sachen."],
                  [("Gladiātōrēs sē virōs clārōs esse putant.",
                    "Die Gladiatoren glauben, dass sie (selbst) berühmte Männer sind."),
                   ("Rōmānī eōs semper bene pūgnāre putant.",
                    "Die Römer glauben, dass diese (die Gladiatoren) immer gut "
                    "kämpfen.")])),
        ("verb_zeiten", ("ire", ["Präsens Aktiv", "Imperfekt Aktiv", "Futur I Aktiv"])),
        ("verb_zeiten", ("ire", ["Perfekt Aktiv", "Plusquamperfekt Aktiv"], False)),
    ],
    13: [
        ("subst", "res"),
        ("merk", ("Verben: Passiv",
                  ["Neben dem Aktiv (der „Tatform“) gibt es das Passiv (die "
                   "„Leideform“). Der Oberbegriff lautet Genus verbi.",
                   "Die Passivformen des Präsensstamms werden aus denselben "
                   "Bauelementen gebildet wie die Aktivformen: Präsensstamm, "
                   "Tempuszeichen, Personalendung.",
                   "Das Passiv hat eigene Personalendungen: -r, -ris, -tur, -mur, "
                   "-minī, -ntur."],
                  [("vocābātur", "er wurde gerufen")])),
        ("zeit", "Imperfekt Passiv"),
        ("zeit", "Präsens Passiv"),
    ],
    14: [
        ("subst", "nomen"),
        ("merk", ("Partizip Perfekt Passiv (PPP)",
                  ["Bei vielen Verben wird das PPP gebildet, indem -tus, a, um an den "
                   "Präsensstamm tritt (vor allem beim v-Perfekt).",
                   "Das PPP wird dekliniert wie die Adjektive der a-/o-Deklination.",
                   "Oft ist es unregelmäßig gebildet; dann lernt man es als vierte "
                   "Stammform mit."],
                  [("necātus, a, um", "getötet"),
                   ("servātus, a, um", "gerettet")])),
        ("stammformen", ("Stammformen mit unregelmäßigem PPP",
                         ["terrere", "ducere", "vincere", "colere"])),
        ("passiv", ("vocare", "Perfekt")),
        ("merk", ("Verwendung des Perfekt Passiv",
                  ["Das Perfekt wird in Erzählungen meist mit dem Präteritum "
                   "wiedergegeben.",
                   "Manchmal bezeichnet das Perfekt Passiv einen Zustand oder ein "
                   "Ergebnis; dann fehlt im Deutschen der Zusatz „worden“.",
                   "Der Infinitiv Perfekt Passiv bezeichnet – wie der Infinitiv "
                   "Perfekt Aktiv – die Vorzeitigkeit."],
                  [("Puellae servātae sunt.",
                    "Die Mädchen wurden gerettet. / Die Mädchen sind gerettet."),
                   ("Puellās servātās esse scīmus.",
                    "Wir wissen, dass die Mädchen gerettet (worden) sind.")])),
        ("passiv", ("vocare", "Plusquamperfekt")),
    ],
}


def tafel_stammformen(db, titel, lemmata):
    """Die vier Stammformen mehrerer Verben untereinander."""
    zeilen = []
    for lemma in lemmata:
        g = _gruppe(db, lemma)
        if not g:
            continue
        formen = {}
        for e in g["entries"]:
            for k, v in (e.get("formen") or {}).items():
                formen.setdefault(k, v)
        zeilen.append((formen.get("infinitiv", lemma), formen.get("praesens", ""),
                       formen.get("perfekt", ""), formen.get("ppp", "")))
    return Tafel(titel, ["Inf. Präs.", "1. Sg. Präs.", "1. Sg. Perf.", "PPP"], zeilen,
                 "Leere Felder gibt das Lehrbuch an dieser Stelle nicht an.")


def _lehrplan_tafeln(db, nummer):
    """Die Tafeln zu den Themen der Buchseite dieser Lektion."""
    ergebnis = []
    for art, wert in LEHRPLAN.get(nummer, []):
        if art == "subst":
            g = _gruppe(db, wert)
            if g:
                ergebnis.append(tafel_substantiv(g))
        elif art == "adj":
            g = _gruppe(db, wert)
            if g:
                ergebnis.append(tafel_adjektiv(g))
        elif art == "pron":
            g = _gruppe(db, wert)
            if g:
                index = _index(g)
                ergebnis.append(Tafel(wert, ["", ""],
                                      [(lab, " / ".join(f))
                                       for (lab, _p), f in index.items()
                                       if f and lab not in ("m", "f", "n")]))
        elif art == "verb_zeiten":
            lemma, zeiten = wert[0], wert[1]
            zusatz = wert[2] if len(wert) > 2 else True
            g = _gruppe(db, lemma)
            if g:
                ergebnis += tafeln_verb_formen(g, zeiten, zusatz)
        elif art == "verb_zeit":
            lemma, zeit = wert
            g = _gruppe(db, lemma)
            if g:
                ergebnis.append(tafel_verb_zeit(g, zeit))
        elif art == "zeit":
            ergebnis.append(tafel_zeit_alle(db, wert))
        elif art == "stammformen":
            titel, lemmata = wert
            ergebnis.append(tafel_stammformen(db, titel, lemmata))
        elif art == "passiv":
            lemma, zeit = wert
            g = _gruppe(db, lemma)
            if g:
                ergebnis.append(tafel_passiv_zusammengesetzt(g, zeit))
        elif art == "merk":
            titel, regeln, beispiele = wert
            ergebnis.append(Merksatz(titel, regeln, beispiele))
    return [t for t in ergebnis if not t.leer()]


def neu_je_lektion(db):
    """{Lektion: [(Art, Bezeichnung, Gruppe), ...]} - was hier zuerst auftaucht."""
    erste, ergebnis = {}, {}
    for g in sorted(db.groups, key=lambda x: x["entries"][0]["lektion"]):
        e = g["entries"][0]
        if g["wortart"] == "Verb" and g.get("conj"):
            schluessel = ("Konjugation", g["conj"])
            name = CONJ_NAMES[g["conj"]]
        elif g["wortart"] == "Substantiv" and e.get("deklination"):
            schluessel = ("Deklination", (e["deklination"], e.get("genus")))
            name = f"{e['deklination']}. Deklination ({e.get('genus')})"
        elif g["wortart"] == "Pronomen" and g.get("par") and g["par"].rows:
            schluessel = ("Pronomen", norm(g["lemma"]))
            name = f"Pronomen {g['lemma']}"
        elif g["wortart"] == "Adjektiv" and g.get("par") and any(
                "Komparativ" in lab for lab, _p, _a in g["par"].rows):
            schluessel = ("Steigerung", "adjektiv")
            name = "Steigerung der Adjektive"
        else:
            continue
        if schluessel in erste:
            continue
        erste[schluessel] = True
        ergebnis.setdefault(e["lektion"], []).append((schluessel[0], name, g))
    return ergebnis


def _beispiele_der_lektion(db, nummer, hoechstens=4):
    """Wenn eine Lektion keine neue Formenlehre bringt: ein paar Tabellen der
    Woerter, die dort vorkommen - je Wortart eines."""
    tafeln, belegt = [], set()
    for g in db.groups:
        if not g.get("par") or not g["par"].rows:
            continue
        if not any(e["lektion"] == nummer for e in g["entries"]):
            continue
        wortart = g["wortart"]
        if wortart in belegt or wortart not in ("Verb", "Substantiv", "Adjektiv", "Pronomen"):
            continue
        belegt.add(wortart)
        if wortart == "Substantiv":
            tafeln.append(tafel_substantiv(g))
        elif wortart == "Adjektiv":
            tafeln.append(tafel_adjektiv(g))
        elif wortart == "Verb":
            index = _index(g)
            zeilen = [(z, " · ".join(x for x in (_form(index, z, p) for p in PERS) if x))
                      for z in ZEITEN if _form(index, z, PERS[0])]
            tafeln.append(Tafel(f"{zitierform(g)} – {CONJ_NAMES.get(g.get('conj'), '')}",
                                ["", ""], zeilen))
        else:
            index = _index(g)
            tafeln.append(Tafel(f"{g['lemma']}", ["", ""],
                                [(lab, " / ".join(f)) for (lab, _p), f in index.items()
                 if f and lab not in ("m", "f", "n")]))
        if len(tafeln) >= hoechstens:
            break
    return [t for t in tafeln if not t.leer()]


def ist_ungeprueft(nummer):
    """True, wenn zu dieser Lektion keine Grammatikseite aus dem Buch vorliegt
    und die Themen deshalb nur aus den Vokabeln abgeleitet sind."""
    return nummer not in LEHRPLAN


def warnung_lektion(nummer):
    return Merksatz(
        f"⚠  Lektion {nummer}: Grammatik noch nicht abgesichert",
        ["Zu dieser Lektion liegt keine Grammatikseite aus dem Lehrbuch vor.",
         "Die Themen unten sind aus den Vokabeln abgeleitet: gezeigt wird, welche "
         "Formenlehre hier zum ersten Mal auftaucht.",
         "Das muss nicht dem entsprechen, was die Lektion wirklich behandelt – "
         "Reihenfolge und Schwerpunkte können abweichen, einzelne Themen fehlen "
         "vielleicht ganz.",
         "Zum Lernen bitte das Buch danebenlegen. Sobald ein Foto der Seite da ist, "
         "verschwindet dieser Hinweis."])


def tafeln_lektion(db, nummer, neu=None):
    # Wo die Grammatikseite des Buches vorliegt, richten sich die Tafeln nach
    # deren Themen (LEHRPLAN); sonst wird nur abgeleitet, was in der Lektion neu
    # dazukommt - und genau davor warnt der erste Block.
    aus_dem_buch = _lehrplan_tafeln(db, nummer)
    if aus_dem_buch:
        return aus_dem_buch

    neu = neu if neu is not None else neu_je_lektion(db)
    tafeln = []
    for art, name, g in neu.get(nummer, []):
        if art == "Konjugation":
            tafeln.append(Tafel(f"Neu: {name} – Muster {zitierform(g)}", ["", ""],
                                [(z, " · ".join(x for x in
                                                (_form(_index(g), z, p) for p in PERS) if x))
                                 for z in ZEITEN if _form(_index(g), z, PERS[0])]))
        elif art == "Deklination":
            tafeln.append(tafel_substantiv(g))
        elif art == "Pronomen":
            index = _index(g)
            tafeln.append(Tafel(f"Neu: {g['lemma']}", ["", ""],
                                [(lab, " / ".join(f)) for (lab, _p), f in index.items()
                 if f and lab not in ("m", "f", "n")]))
        elif art == "Steigerung":
            tafeln += tafeln_steigerung(db)[:1]
    tafeln = [t for t in tafeln if not t.leer()]
    if not tafeln:
        # Keine neue Formenlehre - dann wenigstens Beispiele aus der Lektion
        tafeln = _beispiele_der_lektion(db, nummer)
        if tafeln:
            tafeln.insert(0, Tafel(
                f"Lektion {nummer}", ["", ""],
                [("Hinweis", "keine neue Formenlehre"),
                 ("", "unten ein paar Tabellen zu Wörtern dieser Lektion")]))
    tafeln.insert(0, warnung_lektion(nummer))
    return tafeln


# --------------------------------------------------------------------------
#  Themenliste fuer die Oberflaeche
# --------------------------------------------------------------------------

def themen(db):
    """[(Anzeigename, Schluessel)] - in der Reihenfolge des Auswahlfeldes."""
    liste = [("Konjugationen im Überblick", ("konj", None)),
             ("Unregelmäßige Verben", ("unreg", None)),
             ("Deklinationen im Überblick", ("dekl", None)),
             ("Pronomen", ("pron", None)),
             ("Steigerung der Adjektive", ("steig", None))]
    for zeit in ZEITEN:
        liste.append((f"Zeit: {zeit}", ("zeit", zeit)))
    mit_seiten = lektionen_mit_seiten()
    for nr in sorted({e["lektion"] for e in db.entries}):
        anzahl = mit_seiten.get(nr, 0)
        if ist_ungeprueft(nr):
            marke = "   (ungeprüft)"
        elif anzahl:
            marke = f"   ({anzahl} Buchseite{'n' if anzahl != 1 else ''})"
        else:
            marke = ""
        liste.append((f"Lektion {nr}{marke}", ("lektion", nr)))
    return liste


def tafeln(db, schluessel, neu=None):
    art, wert = schluessel
    if art == "konj":
        return tafeln_konjugationen(db)
    if art == "unreg":
        return tafeln_unregelmaessig(db)
    if art == "dekl":
        return tafeln_deklinationen(db)
    if art == "pron":
        return tafeln_pronomen(db)
    if art == "steig":
        return tafeln_steigerung(db)
    if art == "zeit":
        return [tafel_zeit_alle(db, wert)]
    if art == "lektion":
        return tafeln_lektion(db, wert, neu)
    return []
