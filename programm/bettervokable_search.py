"""
vokabel_core.py  -  gemeinsamer Kern für alle Vokabel-Programme
================================================================
Lädt vokabel_base.json und stellt bereit:

  * norm() / gnorm()       Normalisierung (Längenzeichen, u/v, i/j, Umlaute)
  * VokabelBase            Datenbank + Formenerkennung + Suche + Vorschläge

Andere Skripte (Vokabeltrainer, Quiz, ...) können einfach so starten:

    from vokabel_core import VokabelBase
    db = VokabelBase()                    # lädt vokabel_base.json
    for eintrag in db.entries:            # alle Vokabeln (mit Feld 'lektion')
        ...
    treffer = db.search("rogaverunt")     # Formenerkennung

Die Formenerkennung erzeugt beim Start aus jedem Eintrag alle Formen
(Konjugation / Deklination) und legt sie in einem Index ab.
"""

import json
import re
import sys
import unicodedata
from collections import OrderedDict, defaultdict
from difflib import SequenceMatcher

import pfade

DB_PATH = pfade.VOKABELDATEI

# --------------------------------------------------------------------------
#  Normalisierung
# --------------------------------------------------------------------------

def strip_macrons(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return unicodedata.normalize("NFC", s)


def norm(s: str) -> str:
    """Latein: klein, ohne Makra, u=v, i=j, nur Buchstaben und Leerzeichen."""
    s = strip_macrons(s).lower().replace("j", "i").replace("v", "u")
    s = re.sub(r"[^a-z ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def gnorm(s: str) -> str:
    """Deutsch: klein, ä->a, ö->o, ü->u, ß->ss."""
    s = s.lower()
    for a, b in (("ä", "a"), ("ö", "o"), ("ü", "u"), ("ß", "ss")):
        s = s.replace(a, b)
    s = re.sub(r"[^a-z ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# --------------------------------------------------------------------------
#  Konstanten
# --------------------------------------------------------------------------

PERS = ["1. Pers. Sg.", "2. Pers. Sg.", "3. Pers. Sg.",
        "1. Pers. Pl.", "2. Pers. Pl.", "3. Pers. Pl."]
PERS_IMP = ["2. Pers. Sg.", "2. Pers. Pl."]
CASES = ["Nominativ", "Genitiv", "Dativ", "Akkusativ", "Ablativ", "Vokativ"]

CONJ_NAMES = {"A": "a-Konjugation", "E": "e-Konjugation", "I": "i-Konjugation",
              "FERRE": "unregelmäßig (ferre)",
              "C": "konsonantische Konjugation", "CAP": "kurzvokalische i-Konjugation (capere-Typ)",
              "ESSE": "unregelmäßig (esse)", "POSSE": "unregelmäßig (posse)",
              "IRE": "unregelmäßig (ire)", "VELLE": "unregelmäßig (velle)",
              "NOLLE": "unregelmäßig (nolle)", "INQUAM": "defektiv (inquam)",
              "NOSSE": "Perfekt mit Präsensbedeutung (nosse)"}

# Perfektstämme (mit v/u geschrieben, ohne Makra), die im Buch für Lektion 1-8
# noch nicht angegeben sind. Werden NUR benutzt, wenn die Datenbank kein Perfekt kennt.
_PERFEKT_EXTRA_RAW = {
    "stare": "steti", "ostendere": "ostendi", "vivere": "vixi", "resistere": "restiti",
    "tangere": "tetigi", "accendere": "accendi", "legere": "legi", "scribere": "scripsi",
    "cupere": "cupivi", "incipere": "incepi", "quaerere": "quaesivi", "vendere": "vendidi",
    "convenire": "conveni", "emere": "emi", "considere": "consedi", "attingere": "attigi",
    "repetere": "repetivi", "desinere": "desii", "aperire": "aperui", "providere": "providi",
    "cavere": "cavi", "instare": "institi", "movere": "movi", "ardere": "arsi",
    "circumvenire": "circumveni", "ridere": "risi", "sedere": "sedi", "videre": "vidi",
}
_NO_PERFEKT_PREDICTION_RAW = {"audere", "gaudere", "novisse nosse"}

# Nachgeschlagen wird immer mit norm(); norm() schreibt v->u und j->i.  Die
# Schluessel muessen deshalb ebenfalls normalisiert sein, sonst greift z. B.
# "videre" oder "movere" nie.  Die Werte bleiben in Buchschreibweise.
PERFEKT_EXTRA = {norm(k): v for k, v in _PERFEKT_EXTRA_RAW.items()}
NO_PERFEKT_PREDICTION = {norm(k) for k in _NO_PERFEKT_PREDICTION_RAW}

ESSE_TAB = OrderedDict([
    ("Präsens Aktiv", ["sum", "es", "est", "sumus", "estis", "sunt"]),
    ("Imperfekt Aktiv", ["eram", "eras", "erat", "eramus", "eratis", "erant"]),
    ("Futur I Aktiv", ["ero", "eris", "erit", "erimus", "eritis", "erunt"]),
    ("Perfekt Aktiv", ["fui", "fuisti", "fuit", "fuimus", "fuistis", ["fuerunt", "fuere"]]),
    ("Plusquamperfekt Aktiv", ["fueram", "fueras", "fuerat", "fueramus", "fueratis", "fuerant"]),
    ("Futur II Aktiv", ["fuero", "fueris", "fuerit", "fuerimus", "fueritis", "fuerint"]),
    ("Konjunktiv Präsens Aktiv", ["sim", "sis", "sit", "simus", "sitis", "sint"]),
    ("Konjunktiv Imperfekt Aktiv", ["essem", "esses", "esset", "essemus", "essetis", "essent"]),
    ("Konjunktiv Perfekt Aktiv", ["fuerim", "fueris", "fuerit", "fuerimus", "fueritis", "fuerint"]),
    ("Konjunktiv Plusquamperfekt Aktiv", ["fuissem", "fuisses", "fuisset", "fuissemus", "fuissetis", "fuissent"]),
])
ESSE_IMP = ["es", "este"]

IRE_TAB = OrderedDict([
    ("Präsens Aktiv", ["eo", "is", "it", "imus", "itis", "eunt"]),
    ("Imperfekt Aktiv", ["ibam", "ibas", "ibat", "ibamus", "ibatis", "ibant"]),
    ("Futur I Aktiv", ["ibo", "ibis", "ibit", "ibimus", "ibitis", "ibunt"]),
    ("Perfekt Aktiv", ["ii", ["isti", "iisti"], "iit", "iimus", ["istis", "iistis"], ["ierunt", "iere"]]),
    ("Plusquamperfekt Aktiv", ["ieram", "ieras", "ierat", "ieramus", "ieratis", "ierant"]),
    ("Futur II Aktiv", ["iero", "ieris", "ierit", "ierimus", "ieritis", "ierint"]),
    ("Konjunktiv Präsens Aktiv", ["eam", "eas", "eat", "eamus", "eatis", "eant"]),
    ("Konjunktiv Imperfekt Aktiv", ["irem", "ires", "iret", "iremus", "iretis", "irent"]),
])
IRE_IMP = ["i", "ite"]

VELLE_TAB = OrderedDict([
    ("Präsens Aktiv", ["volo", "vis", "vult", "volumus", "vultis", "volunt"]),
    ("Imperfekt Aktiv", ["volebam", "volebas", "volebat", "volebamus", "volebatis", "volebant"]),
    ("Futur I Aktiv", ["volam", "voles", "volet", "volemus", "voletis", "volent"]),
    ("Perfekt Aktiv", ["volui", "voluisti", "voluit", "voluimus", "voluistis", ["voluerunt", "voluere"]]),
    ("Plusquamperfekt Aktiv", ["volueram", "volueras", "voluerat", "volueramus", "volueratis", "voluerant"]),
    ("Konjunktiv Präsens Aktiv", ["velim", "velis", "velit", "velimus", "velitis", "velint"]),
    ("Konjunktiv Imperfekt Aktiv", ["vellem", "velles", "vellet", "vellemus", "velletis", "vellent"]),
])
NOLLE_TAB = OrderedDict([
    ("Präsens Aktiv", ["nolo", ["non vis", "nonvis"], ["non vult", "nonvult"], "nolumus", ["non vultis", "nonvultis"], "nolunt"]),
    ("Imperfekt Aktiv", ["nolebam", "nolebas", "nolebat", "nolebamus", "nolebatis", "nolebant"]),
    ("Futur I Aktiv", ["nolam", "noles", "nolet", "nolemus", "noletis", "nolent"]),
    ("Perfekt Aktiv", ["nolui", "noluisti", "noluit", "noluimus", "noluistis", ["noluerunt", "noluere"]]),
    ("Plusquamperfekt Aktiv", ["nolueram", "nolueras", "noluerat", "nolueramus", "nolueratis", "noluerant"]),
    ("Konjunktiv Präsens Aktiv", ["nolim", "nolis", "nolit", "nolimus", "nolitis", "nolint"]),
    ("Konjunktiv Imperfekt Aktiv", ["nollem", "nolles", "nollet", "nollemus", "nolletis", "nollent"]),
])

# ferre bildet den Praesensstamm unregelmaessig (fers, fert, ferre, ferrem).
# Perfekt und PPP stehen in der Vokabeldatei und werden normal weiterverarbeitet.
FERRE_TAB = OrderedDict([
    ("Präsens Aktiv", ["fero", "fers", "fert", "ferimus", "fertis", "ferunt"]),
    ("Imperfekt Aktiv", ["ferebam", "ferebas", "ferebat", "ferebamus", "ferebatis", "ferebant"]),
    ("Futur I Aktiv", ["feram", "feres", "feret", "feremus", "feretis", "ferent"]),
    ("Konjunktiv Präsens Aktiv", ["feram", "feras", "ferat", "feramus", "feratis", "ferant"]),
    ("Konjunktiv Imperfekt Aktiv", ["ferrem", "ferres", "ferret", "ferremus", "ferretis", "ferrent"]),
    ("Präsens Passiv", ["feror", ["ferris", "ferre"], "fertur", "ferimur", "ferimini", "feruntur"]),
    ("Imperfekt Passiv", ["ferebar", ["ferebaris", "ferebare"], "ferebatur", "ferebamur",
                          "ferebamini", "ferebantur"]),
    ("Futur I Passiv", ["ferar", ["fereris", "ferere"], "feretur", "feremur", "feremini",
                        "ferentur"]),
    ("Konjunktiv Präsens Passiv", ["ferar", ["feraris", "ferare"], "feratur", "feramur",
                                   "feramini", "ferantur"]),
    ("Konjunktiv Imperfekt Passiv", ["ferrer", ["ferreris", "ferrere"], "ferretur", "ferremur",
                                     "ferremini", "ferrentur"]),
])
FERRE_IMP = ["fer", "ferte"]

PRES = {"A": ["o", "as", "at", "amus", "atis", "ant"],
        "E": ["eo", "es", "et", "emus", "etis", "ent"],
        "I": ["io", "is", "it", "imus", "itis", "iunt"],
        "C": ["o", "is", "it", "imus", "itis", "unt"],
        "CAP": ["io", "is", "it", "imus", "itis", "iunt"]}
IMPF_BASE = {"A": "aba", "E": "eba", "I": "ieba", "C": "eba", "CAP": "ieba"}
FUT = {"A": ["abo", "abis", "abit", "abimus", "abitis", "abunt"],
       "E": ["ebo", "ebis", "ebit", "ebimus", "ebitis", "ebunt"],
       "I": ["iam", "ies", "iet", "iemus", "ietis", "ient"],
       "C": ["am", "es", "et", "emus", "etis", "ent"],
       "CAP": ["iam", "ies", "iet", "iemus", "ietis", "ient"]}
PASS_PRES = {"A": ["or", ["aris", "are"], "atur", "amur", "amini", "antur"],
             "E": ["eor", ["eris", "ere"], "etur", "emur", "emini", "entur"],
             "I": ["ior", ["iris", "ire"], "itur", "imur", "imini", "iuntur"],
             "C": ["or", ["eris", "ere"], "itur", "imur", "imini", "untur"],
             "CAP": ["ior", ["eris", "ere"], "itur", "imur", "imini", "iuntur"]}
FUT_PASS = {"A": ["abor", ["aberis", "abere"], "abitur", "abimur", "abimini", "abuntur"],
            "E": ["ebor", ["eberis", "ebere"], "ebitur", "ebimur", "ebimini", "ebuntur"],
            "I": ["iar", ["ieris", "iere"], "ietur", "iemur", "iemini", "ientur"],
            "C": ["ar", ["eris", "ere"], "etur", "emur", "emini", "entur"],
            "CAP": ["iar", ["ieris", "iere"], "ietur", "iemur", "iemini", "ientur"]}
IMP = {"A": ["a", "ate"], "E": ["e", "ete"], "I": ["i", "ite"], "C": ["e", "ite"], "CAP": ["e", "ite"]}
INF = {"A": "are", "E": "ere", "I": "ire", "C": "ere", "CAP": "ere"}
INF_PASS = {"A": "ari", "E": "eri", "I": "iri", "C": "i", "CAP": "i"}
SUBJ = {"A": ["em", "es", "et", "emus", "etis", "ent"],
        "E": ["eam", "eas", "eat", "eamus", "eatis", "eant"],
        "I": ["iam", "ias", "iat", "iamus", "iatis", "iant"],
        "C": ["am", "as", "at", "amus", "atis", "ant"],
        "CAP": ["iam", "ias", "iat", "iamus", "iatis", "iant"]}
PPA = {"A": "ant", "E": "ent", "I": "ient", "C": "ent", "CAP": "ient"}
SIX = ["m", "s", "t", "mus", "tis", "nt"]
SIX_PASS = ["r", "ris", "tur", "mur", "mini", "ntur"]

PRON_ADJ_STEMS = {"un", "ull", "null", "sol"}   # Genitiv -ius, Dativ -i

# ---- Steigerung -----------------------------------------------------------
# Superlativ auf -limus statt -issimus (Schluessel normalisiert nachgeschlagen)
SUP_LIMUS = {norm(x) for x in ("facilis", "difficilis", "similis", "dissimilis",
                               "gracilis", "humilis")}
# Adjektive mit eigener Steigerung.  (Komparativ m/f, Komparativ n, Superlativstamm)
IRREG_COMP = {norm(k): v for k, v in {
    "bonus": ("melior", "melius", "optim"),
    "malus": ("peior", "peius", "pessim"),
    "magnus": ("maior", "maius", "maxim"),
    "parvus": ("minor", "minus", "minim"),
    "multus": ("plus", "plus", "plurim"),
}.items()}
# Wo eine Steigerung keinen Sinn ergibt (Possessiva, Zahlwoerter, Pronominal-
# adjektive) oder wo das Lemma selbst schon Komparativ/Superlativ ist.
NO_COMPARISON = {norm(x) for x in (
    "meus", "tuus", "suus", "noster", "vester", "unus", "nullus", "ullus",
    "nonnullus", "alius", "solus", "ceteri", "cunctus", "paucus", "plerique",
    "plurimus", "optimus", "summus", "primus", "superior", "reliquus",
    "futurus", "contentus")}
# Adverb-Bildung: unregelmaessig (Positiv, Komparativ, Superlativ)
IRREG_ADV = {norm(k): v for k, v in {
    "bonus": ("bene", "melius", "optime"),
    "malus": ("male", "peius", "pessime"),
    "magnus": ("magnopere", "magis", "maxime"),
    "parvus": ("parum", "minus", "minime"),
    "multus": ("multum", "plus", "plurimum"),
    "facilis": ("facile", "facilius", "facillime"),
}.items()}
# Steigerung fuer Adverbien, die als eigene Vokabel in der Datenbank stehen
ADV_COMP_EXTRA = {norm(k): v for k, v in {
    "saepe": ("saepius", "saepissime"),
    "diu": ("diutius", "diutissime"),
    "prope": ("propius", "proxime"),
    "bene": ("melius", "optime"),
    "male": ("peius", "pessime"),
    "libenter": ("libentius", "libentissime"),
}.items()}

# ---- Gerundium / Gerundivum / PFA ----------------------------------------
GERUND = {"A": "and", "E": "end", "I": "iend", "C": "end", "CAP": "iend"}

PRON_FORMS = {
    "is": [("Nominativ Sg. m", "is"), ("Nominativ Sg. f", "ea"), ("Nominativ/Akkusativ Sg. n", "id"),
           ("Genitiv Sg.", "eius"), ("Dativ Sg.", "ei"), ("Akkusativ Sg. m", "eum"),
           ("Akkusativ Sg. f", "eam"), ("Ablativ Sg. m/n", "eo"), ("Ablativ Sg. f", "ea"),
           ("Nominativ Pl. m", "ei"), ("Nominativ Pl. m", "ii"), ("Nominativ Pl. f", "eae"),
           ("Nominativ/Akkusativ Pl. n", "ea"), ("Genitiv Pl. m/n", "eorum"), ("Genitiv Pl. f", "earum"),
           ("Dativ/Ablativ Pl.", "eis"), ("Dativ/Ablativ Pl.", "iis"),
           ("Akkusativ Pl. m", "eos"), ("Akkusativ Pl. f", "eas")],
    "qui": [("Nominativ Sg. f / Pl. f,n", "quae"), ("Nominativ/Akkusativ Sg. n", "quod"),
            ("Genitiv Sg.", "cuius"), ("Dativ Sg.", "cui"), ("Akkusativ Sg. m", "quem"),
            ("Akkusativ Sg. f", "quam"), ("Ablativ Sg. m/n", "quo"), ("Ablativ Sg. f", "qua"),
            ("Nominativ Pl. m", "qui"), ("Genitiv Pl. m/n", "quorum"), ("Genitiv Pl. f", "quarum"),
            ("Dativ/Ablativ Pl.", "quibus"), ("Akkusativ Pl. m", "quos"), ("Akkusativ Pl. f", "quas")],
    "hic": [("Nominativ Sg. m", "hic"), ("Nominativ Sg. f", "haec"),
             ("Nominativ/Akkusativ Sg. n", "hoc"), ("Genitiv Sg.", "huius"),
             ("Dativ Sg.", "huic"), ("Akkusativ Sg. m", "hunc"),
             ("Akkusativ Sg. f", "hanc"), ("Ablativ Sg. m/n", "hoc"),
             ("Ablativ Sg. f", "hac"), ("Nominativ Pl. m", "hi"),
             ("Nominativ Pl. f", "hae"), ("Nominativ/Akkusativ Pl. n", "haec"),
             ("Genitiv Pl. m/n", "horum"), ("Genitiv Pl. f", "harum"),
             ("Dativ/Ablativ Pl.", "his"), ("Akkusativ Pl. m", "hos"),
             ("Akkusativ Pl. f", "has")],
    "ille": [("Nominativ Sg. m", "ille"), ("Nominativ Sg. f", "illa"),
             ("Nominativ/Akkusativ Sg. n", "illud"), ("Genitiv Sg.", "illius"),
             ("Dativ Sg.", "illi"), ("Akkusativ Sg. m", "illum"),
             ("Akkusativ Sg. f", "illam"), ("Ablativ Sg. m/n", "illo"),
             ("Ablativ Sg. f", "illa"), ("Nominativ Pl. m", "illi"),
             ("Nominativ Pl. f", "illae"), ("Nominativ/Akkusativ Pl. n", "illa"),
             ("Genitiv Pl. m/n", "illorum"), ("Genitiv Pl. f", "illarum"),
             ("Dativ/Ablativ Pl.", "illis"), ("Akkusativ Pl. m", "illos"),
             ("Akkusativ Pl. f", "illas")],
    "iste": [("Nominativ Sg. m", "iste"), ("Nominativ Sg. f", "ista"),
             ("Nominativ/Akkusativ Sg. n", "istud"), ("Genitiv Sg.", "istius"),
             ("Dativ Sg.", "isti"), ("Akkusativ Sg. m", "istum"),
             ("Akkusativ Sg. f", "istam"), ("Ablativ Sg. m/n", "isto"),
             ("Ablativ Sg. f", "ista"), ("Nominativ Pl. m", "isti"),
             ("Nominativ Pl. f", "istae"), ("Nominativ/Akkusativ Pl. n", "ista"),
             ("Genitiv Pl. m/n", "istorum"), ("Genitiv Pl. f", "istarum"),
             ("Dativ/Ablativ Pl.", "istis"), ("Akkusativ Pl. m", "istos"),
             ("Akkusativ Pl. f", "istas")],
    "idem": [("Nominativ Sg. m", "idem"), ("Nominativ Sg. f", "eadem"),
             ("Nominativ/Akkusativ Sg. n", "idem"), ("Genitiv Sg.", "eiusdem"),
             ("Dativ Sg.", "eidem"), ("Akkusativ Sg. m", "eundem"),
             ("Akkusativ Sg. f", "eandem"), ("Ablativ Sg. m/n", "eodem"),
             ("Ablativ Sg. f", "eadem"), ("Nominativ Pl. m", "eidem"),
             ("Nominativ Pl. m", "idem"), ("Nominativ Pl. f", "eaedem"),
             ("Nominativ/Akkusativ Pl. n", "eadem"), ("Genitiv Pl. m/n", "eorundem"),
             ("Genitiv Pl. f", "earundem"), ("Dativ/Ablativ Pl.", "eisdem"),
             ("Dativ/Ablativ Pl.", "isdem"), ("Akkusativ Pl. m", "eosdem"),
             ("Akkusativ Pl. f", "easdem")],
    "ego": [("Genitiv Sg.", "mei")],
    "tu": [("Genitiv Sg.", "tui")],
    "nos": [("Genitiv Pl.", "nostri"), ("Genitiv Pl.", "nostrum")],
    "vos": [("Genitiv Pl.", "vestri"), ("Genitiv Pl.", "vestrum"), ("Dativ/Ablativ Pl.", "vobis")],
}

PRON_FORMS = {norm(k): v for k, v in PRON_FORMS.items()}

FORMEN_LABEL = {
    "praesens": "Präsens (1. Sg.)", "praesens_3sg": "Präsens 3. Sg.", "praesens_3pl": "Präsens 3. Pl.",
    "infinitiv": "Infinitiv", "perfekt": "Perfekt (1. Sg.)", "ppp": "PPP",
    "nominativ": "Nominativ", "genitiv": "Genitiv", "genitiv_pl": "Genitiv Pl.",
    "m": "m", "f": "f", "n": "n",
}


# --------------------------------------------------------------------------
#  Formen-Container
# --------------------------------------------------------------------------

class Par:
    """Sammelt (Label, Person, [Varianten]) Zeilen."""

    def __init__(self):
        self.rows = []

    def add(self, label, forms, persons=None):
        for i, f in enumerate(forms):
            alts = f if isinstance(f, list) else [f]
            self.rows.append((label, persons[i] if persons else None, alts))

    def add_one(self, label, form):
        self.rows.append((label, None, form if isinstance(form, list) else [form]))


# --------------------------------------------------------------------------
#  Verben
# --------------------------------------------------------------------------

_ESSE_INF = {norm(x) for x in ("esse", "adesse", "abesse", "deesse")}
_IRE_INF = {norm(x) for x in ("ire", "adire", "inire", "abire", "redire", "perire",
                              "subire", "exire", "transire", "praeterire")}
_POSSE_INF = norm("posse")
_VELLE_INF = norm("velle")
_NOLLE_INF = norm("nolle")


def _verb_class(g):
    inf_raw = g["inf"]
    ninf = norm(inf_raw)
    if "/" in inf_raw:
        return "NOSSE"
    if g["lemma"] == "inquam":
        return "INQUAM"
    if ninf in _ESSE_INF:
        return "ESSE"
    if ninf == _POSSE_INF:
        return "POSSE"
    if ninf in _IRE_INF:
        return "IRE"
    if ninf.endswith("ferre"):
        return "FERRE"
    if ninf == _VELLE_INF:
        return "VELLE"
    if ninf == _NOLLE_INF:
        return "NOLLE"
    if inf_raw.endswith("āre"):
        return "A"
    if inf_raw.endswith("ēre"):
        return "E"
    if inf_raw.endswith("īre"):
        return "I"
    if inf_raw.endswith("ere"):
        pres = norm(g.get("praes", ""))
        if pres.endswith("io"):
            return "CAP"
        if pres.endswith("eo"):
            return "E"
        return "C"
    # Rueckfallebene, wenn im Lemma keine Laengenzeichen stehen
    if ninf.endswith("are"):
        return "A"
    if ninf.endswith("ire"):
        return "I"
    if ninf.endswith("ere"):
        return "E" if norm(g.get("praes", "")).endswith("eo") else "C"
    return None


def _prefixed(tab, prefix, fix=None):
    out = OrderedDict()
    for label, forms in tab.items():
        new = []
        for f in forms:
            alts = f if isinstance(f, list) else [f]
            res = []
            for a in alts:
                b = fix(prefix, a) if fix else prefix + a
                res.append(b)
                if prefix == "ab" and a.startswith("f"):
                    res.append("a" + a)
            new.append(res if len(res) > 1 else res[0])
        out[label] = new
    return out


def _posse_fix(_, a):
    if a.startswith("ess"):
        return "pos" + a[2:]
    if a.startswith("s"):
        return "pos" + a
    if a.startswith("fu"):
        return "potu" + a[2:]
    return "pot" + a


def _adj12_rows(par, stem, nom_m, nom_f, nom_n, prefix="", sg=True, pl=True, pron=False):
    """Deklination -us/-a/-um (bzw. -er/-a/-um)."""
    N, G, D, A, B, V = range(6)
    gen_sg = [stem + "i"] + ([stem + "ius"] if stem in PRON_ADJ_STEMS else [])
    dat_sg = [stem + "o"] + ([stem + "i"] if stem in PRON_ADJ_STEMS else [])
    if stem == "ali":
        gen_sg, dat_sg = ["alius"], ["alii"]
    voc_m = [stem + "e"] + ([stem] if stem.endswith("i") else []) if nom_m.endswith("us") else [nom_m]
    tabs = {
        ("m", "Sg."): [nom_m, gen_sg, dat_sg, stem + "um", stem + "o", voc_m],
        ("f", "Sg."): [nom_f, [stem + "ae"] + ([stem + "ius"] if stem in PRON_ADJ_STEMS else []),
                       [stem + "ae"] + ([stem + "i"] if stem in PRON_ADJ_STEMS else []),
                       stem + "am", stem + "a", nom_f],
        ("n", "Sg."): [nom_n, gen_sg, dat_sg, nom_n, stem + "o", nom_n],
        ("m", "Pl."): [stem + "i", stem + "orum", stem + "is", stem + "os", stem + "is", stem + "i"],
        ("f", "Pl."): [stem + "ae", stem + "arum", stem + "is", stem + "as", stem + "is", stem + "ae"],
        ("n", "Pl."): [stem + "a", stem + "orum", stem + "is", stem + "a", stem + "is", stem + "a"],
    }
    if stem == "ali":   # alius: gleiche Formen f/n
        tabs[("f", "Sg.")][1] = ["alius"]; tabs[("f", "Sg.")][2] = ["alii"]
    for (g, num), forms in tabs.items():
        if (num == "Sg." and not sg) or (num == "Pl." and not pl):
            continue
        for ci, f in enumerate(forms):
            par.add_one(f"{prefix}{CASES[ci]} {num} {g}", f)


def _adj3_rows(par, stem, nom_m, nom_f, nom_n, prefix="", comparative=False):
    """Deklination der 3. Dekl. (gravis, celer, ingens, ...)."""
    abl = [stem + "i", stem + "e"]
    if comparative:
        abl = [stem + "e", stem + "i"]
    pl_n = stem + ("a" if comparative else "ia")
    g_pl = [stem + "um"] if comparative else [stem + "ium", stem + "um"]
    mf = {"Sg.": [None, stem + "is", stem + "i", stem + "em", abl, None],
          "Pl.": [stem + "es", g_pl, stem + "ibus", [stem + "es", stem + "is"], stem + "ibus", stem + "es"]}
    n = {"Sg.": [nom_n, stem + "is", stem + "i", nom_n, abl, nom_n],
         "Pl.": [pl_n, g_pl, stem + "ibus", pl_n, stem + "ibus", pl_n]}
    for g, nom in (("m", nom_m), ("f", nom_f)):
        for num in ("Sg.", "Pl."):
            for ci, f in enumerate(mf[num]):
                if f is None:
                    f = nom
                par.add_one(f"{prefix}{CASES[ci]} {num} {g}", f)
    for num in ("Sg.", "Pl."):
        for ci, f in enumerate(n[num]):
            par.add_one(f"{prefix}{CASES[ci]} {num} n", f)


def _to_passive(forms):
    """Sechs Aktivformen in die entsprechenden Passivformen umschreiben."""
    out = []
    for i, f in enumerate(forms):
        if i == 0:
            out.append(f[:-1] + "r" if f.endswith("m") else f + "r")
        elif i == 1:
            out.append([f[:-1] + "ris", f[:-1] + "re"])
        elif i == 2:
            out.append(f[:-1] + "tur")
        elif i == 3:
            out.append(f[:-3] + "mur")
        elif i == 4:
            out.append(f[:-3] + "mini")
        else:
            out.append(f[:-2] + "ntur")
    return out


def _comparison_rows(par, lemma, stem, nom_m, dritte):
    """Komparativ, Superlativ und Adverb zu einem Adjektiv.

    stem    Stamm ohne Endung (alt-, fort-, pulchr-)
    nom_m   Nominativ Sg. m. (alt-us, pulcher, acer) – fuer -errimus gebraucht
    dritte  True bei Adjektiven der 3. Deklination (fortis, ingens)
    """
    nl = norm(lemma)
    if nl in NO_COMPARISON:
        return
    if nl in IRREG_COMP:
        k_m, k_n, sup_stem = IRREG_COMP[nl]
        _adj3_rows(par, k_m if k_m.endswith("or") else k_m, k_m, k_m, k_n,
                   prefix="Komparativ ", comparative=True)
        if k_m == "plus":                       # plus, pluris; Pl. plures, plura
            for lab, x in (("Nominativ/Akkusativ Sg. n", "plus"), ("Genitiv Sg.", "pluris"),
                           ("Nominativ/Akkusativ Pl. m/f", "plures"), ("Nominativ/Akkusativ Pl. n", "plura"),
                           ("Genitiv Pl.", "plurium"), ("Dativ/Ablativ Pl.", "pluribus")):
                par.add_one("Komparativ " + lab, x)
    else:
        sup_stem = None
        _adj3_rows(par, stem + "ior", stem + "ior", stem + "ior", stem + "ius",
                   prefix="Komparativ ", comparative=True)

    # ---- Superlativ ----
    if sup_stem is None:
        if nom_m.endswith("er"):                # pulcher -> pulcherrimus, acer -> acerrimus
            sup_stem = nom_m + "rim"
        elif nl in SUP_LIMUS:                   # facilis -> facillimus
            sup_stem = stem + "lim"
        else:
            sup_stem = stem + "issim"
    _adj12_rows(par, sup_stem, sup_stem + "us", sup_stem + "a", sup_stem + "um",
                prefix="Superlativ ")

    # ---- Adverb (Positiv / Komparativ / Superlativ) ----
    if nl in IRREG_ADV:
        pos, comp, sup = IRREG_ADV[nl]
    else:
        if dritte:
            pos = stem + ("er" if stem.endswith("nt") else "iter")
        else:
            pos = stem + "e"
        comp = (IRREG_COMP[nl][1] if nl in IRREG_COMP else stem + "ius")
        sup = sup_stem + "e"
    par.add_one("Adverb", pos)
    par.add_one("Adverb Komparativ", comp)
    par.add_one("Adverb Superlativ", sup)


def _verb_par(g):
    par = Par()
    conj = g["conj"]
    lemma_n = norm(g["inf"])
    if conj == "ESSE":
        prefix = lemma_n[:-4]
        for label, forms in _prefixed(ESSE_TAB, prefix).items():
            par.add(label, forms, PERS)
        par.add("Imperativ Aktiv", [prefix + x for x in ESSE_IMP], PERS_IMP)
        par.add_one("Infinitiv Präsens", prefix + "esse")
        par.add_one("Infinitiv Perfekt", prefix + "fuisse")
        return par
    if conj == "POSSE":
        for label, forms in _prefixed(ESSE_TAB, "", _posse_fix).items():
            par.add(label, forms, PERS)
        par.add_one("Infinitiv Präsens", "posse")
        par.add_one("Infinitiv Perfekt", "potuisse")
        return par
    if conj == "IRE":
        prefix = lemma_n[:-3]
        for label, forms in _prefixed(IRE_TAB, prefix).items():
            par.add(label, forms, PERS)
        par.add("Imperativ Aktiv", [prefix + x for x in IRE_IMP], PERS_IMP)
        par.add_one("Infinitiv Präsens", prefix + "ire")
        par.add_one("Infinitiv Perfekt", [prefix + "isse", prefix + "iisse"])
        return par
    if conj in ("VELLE", "NOLLE"):
        tab = VELLE_TAB if conj == "VELLE" else NOLLE_TAB
        for label, forms in tab.items():
            par.add(label, forms, PERS)
        if conj == "NOLLE":
            par.add("Imperativ Aktiv", ["noli", "nolite"], PERS_IMP)
            par.add_one("Infinitiv Präsens", "nolle"); par.add_one("Infinitiv Perfekt", "noluisse")
        else:
            par.add_one("Infinitiv Präsens", "velle"); par.add_one("Infinitiv Perfekt", "voluisse")
        return par
    if conj == "INQUAM":
        par.add("Präsens Aktiv", ["inquam", "inquis", "inquit", "inquimus", "inquitis", "inquiunt"], PERS)
        return par
    if conj == "NOSSE":
        par.add_one("Infinitiv", ["nosse", "novisse"])
        pf = "nov"
        par.add("Perfekt Aktiv (Präsensbedeutung)", [pf + "i", pf + "isti", pf + "it", pf + "imus", pf + "istis", [pf + "erunt", pf + "ere"]], PERS)
        par.add("Plusquamperfekt Aktiv (Imperfektbedeutung)", [pf + x for x in ["eram", "eras", "erat", "eramus", "eratis", "erant"]], PERS)
        par.add("Futur II Aktiv (Futurbedeutung)", [pf + x for x in ["ero", "eris", "erit", "erimus", "eritis", "erint"]], PERS)
        return par

    s = g["stem"]
    if conj == "FERRE":
        # s ist hier die Vorsilbe (af-, au-, con-, per-, re-, in-, "")
        for label, forms in _prefixed(FERRE_TAB, s).items():
            par.add(label, forms, PERS)
        par.add("Imperativ Aktiv", [s + x for x in FERRE_IMP], PERS_IMP)
        par.add_one("Infinitiv Präsens Aktiv", s + "ferre")
        par.add_one("Infinitiv Präsens Passiv", s + "ferri")
        _adj3_rows(par, s + "ferent", s + "ferens", s + "ferens", s + "ferens",
                   prefix="Partizip Präsens (PPA) ")
        ger = s + "ferend"
        par.add_one("Gerundium Genitiv", ger + "i")
        par.add_one("Gerundium Dativ/Ablativ", [ger + "o"])
        par.add_one("Gerundium Akkusativ", ger + "um")
        _adj12_rows(par, ger, ger + "us", ger + "a", ger + "um", prefix="Gerundivum ")
        return _verb_perfekt_ppp(par, g)
    # ---- Präsensstamm ----
    par.add("Präsens Aktiv", [s + x for x in PRES[conj]], PERS)
    par.add("Imperfekt Aktiv", [s + IMPF_BASE[conj] + x for x in SIX], PERS)
    par.add("Futur I Aktiv", [s + x for x in FUT[conj]], PERS)
    imp = [s + x for x in IMP[conj]]
    if conj in ("C", "CAP") and s.endswith(("duc", "dic", "fac")):
        imp[0] = s
    par.add("Imperativ Aktiv", imp, PERS_IMP)
    par.add_one("Infinitiv Präsens Aktiv", s + INF[conj])
    par.add("Präsens Passiv", [[s + a for a in x] if isinstance(x, list) else s + x for x in PASS_PRES[conj]], PERS)
    par.add("Imperfekt Passiv", [s + IMPF_BASE[conj] + x for x in SIX_PASS], PERS)
    par.add("Futur I Passiv", [[s + a for a in x] if isinstance(x, list) else s + x for x in FUT_PASS[conj]], PERS)
    par.add_one("Infinitiv Präsens Passiv", s + INF_PASS[conj])
    subj_pres = [s + x for x in SUBJ[conj]]
    subj_impf = [s + INF[conj] + x for x in SIX]
    par.add("Konjunktiv Präsens Aktiv", subj_pres, PERS)
    par.add("Konjunktiv Imperfekt Aktiv", subj_impf, PERS)
    par.add("Konjunktiv Präsens Passiv", _to_passive(subj_pres), PERS)
    par.add("Konjunktiv Imperfekt Passiv", _to_passive(subj_impf), PERS)
    # ---- Gerundium / Gerundivum ----
    ger = s + GERUND[conj]
    par.add_one("Gerundium Genitiv", ger + "i")
    par.add_one("Gerundium Dativ/Ablativ", [ger + "o"])
    par.add_one("Gerundium Akkusativ", ger + "um")
    _adj12_rows(par, ger, ger + "us", ger + "a", ger + "um", prefix="Gerundivum ")
    _adj3_rows(par, s + PPA[conj], s + PPA[conj] + "s", s + PPA[conj] + "s", s + PPA[conj] + "s",
               prefix="Partizip Präsens (PPA) ")
    return _verb_perfekt_ppp(par, g)


def _verb_perfekt_ppp(par, g):
    """Perfektstamm, PPP, PFA, Supinum und die zusammengesetzten Infinitive.
    Gemeinsam fuer die regelmaessigen Klassen und fuer ferre."""
    # ---- Perfektstamm ----
    note = {"buch": "",
            "nachgetragen": "  [Perfektstamm nicht im Buch, ergänzt]",
            "geraten": "  [Perfektstamm nicht im Buch, regelmäßig gebildet – ungeprüft]"
            }[g.get("pf_src", "buch")]
    for p in g["pf_stems"]:
        par.add("Perfekt Aktiv" + note, [p + "i", p + "isti", p + "it", p + "imus", p + "istis", [p + "erunt", p + "ere"]], PERS)
        par.add("Plusquamperfekt Aktiv" + note, [p + x for x in ["eram", "eras", "erat", "eramus", "eratis", "erant"]], PERS)
        par.add("Futur II Aktiv" + note, [p + x for x in ["ero", "eris", "erit", "erimus", "eritis", "erint"]], PERS)
        par.add_one("Infinitiv Perfekt Aktiv" + note, p + "isse")
        par.add("Konjunktiv Perfekt Aktiv" + note, [p + x for x in ["erim", "eris", "erit", "erimus", "eritis", "erint"]], PERS)
        par.add("Konjunktiv Plusquamperfekt Aktiv" + note, [p + x for x in ["issem", "isses", "isset", "issemus", "issetis", "issent"]], PERS)
        # Kontrahierte Formen (rogasti, audisti, nosti ...)
        c = None
        if p.endswith("av"):
            c = p[:-2] + "a"
        elif p.endswith("iv"):
            c = p[:-2] + "i"
        elif p.endswith("nov"):
            c = p[:-3] + "no"
        if c:
            par.rows.append(("Perfekt Aktiv" + note, PERS[1], [c + "sti"]))
            par.rows.append(("Perfekt Aktiv" + note, PERS[4], [c + "stis"]))
            par.rows.append(("Perfekt Aktiv" + note, PERS[5], [c + "runt"]))
            par.rows.append(("Infinitiv Perfekt Aktiv" + note, None, [c + "sse"]))
            par.add("Plusquamperfekt Aktiv" + note, [c + x for x in ["ram", "ras", "rat", "ramus", "ratis", "rant"]], PERS)
            par.add("Konjunktiv Plusquamperfekt Aktiv" + note, [c + x for x in ["ssem", "sses", "sset", "ssemus", "ssetis", "ssent"]], PERS)
    # ---- PPP ----
    if g["ppp_stem"]:
        st = g["ppp_stem"]
        pn = "" if g["ppp_known"] else " [regelmäßig gebildet]"
        _adj12_rows(par, st, st + "us", st + "a", st + "um", prefix="PPP" + pn + " ")
        # ---- PFA (Partizip Futur Aktiv) ----
        _adj12_rows(par, st + "ur", st + "urus", st + "ura", st + "urum",
                    prefix="PFA" + pn + " ")
        # ---- Supinum ----
        par.add_one("Supinum I" + pn, st + "um")
        par.add_one("Supinum II" + pn, st + "u")
        # ---- zusammengesetzte Infinitive ----
        par.add_one("Infinitiv Perfekt Passiv" + pn,
                    [st + "um esse", st + "am esse", st + "os esse"])
        par.add_one("Infinitiv Futur Aktiv" + pn,
                    [st + "urum esse", st + "uram esse", st + "uros esse"])
    return par


def _prepare_verb_group(g):
    entries = g["entries"]
    def first(key):
        for e in entries:
            v = e["formen"].get(key)
            if v:
                return v
        return ""
    g["inf"] = first("infinitiv")
    g["praes"] = first("praesens")
    g["perf"] = first("perfekt")
    g["ppp"] = first("ppp")
    g["conj"] = _verb_class(g)
    if g["conj"] in ("A", "E", "I", "C", "CAP", "FERRE"):
        inf = strip_macrons(g["inf"])
        # Bei ferre ist der "Stamm" die Vorsilbe: afferre -> af
        g["stem"] = norm(g["inf"])[:-5] if g["conj"] == "FERRE" else inf[:-3]
        ninf = norm(g["inf"])
        pf_known = bool(g["perf"])
        pf_src = "buch"
        stems = []
        if g["perf"]:
            p = strip_macrons(g["perf"])
            stems = [p[:-1] if p.endswith("i") else p]
        elif ninf in PERFEKT_EXTRA:
            stems = [strip_macrons(PERFEKT_EXTRA[ninf])[:-1]]
            pf_src = "nachgetragen"
        elif ninf not in NO_PERFEKT_PREDICTION:
            s = g["stem"]
            pred = {"A": s + "av", "I": s + "iv", "E": s + "u"}.get(g["conj"])
            stems = [pred] if pred else []
            pf_src = "geraten" if stems else "buch"
        g["pf_stems"], g["pf_known"], g["pf_src"] = stems, pf_known, pf_src
        g["ppp_stem"], g["ppp_known"] = None, False
        if g["ppp"]:
            pp = strip_macrons(g["ppp"])
            g["ppp_stem"] = pp[:-2] if pp.endswith("um") else pp
            g["ppp_known"] = True
        elif g["conj"] == "A":
            g["ppp_stem"] = g["stem"] + "at"
        elif g["conj"] == "I":
            g["ppp_stem"] = g["stem"] + "it"


# --------------------------------------------------------------------------
#  Substantive / Adjektive
# --------------------------------------------------------------------------

def _noun_par(e):
    f = e["formen"]
    nom, gen = strip_macrons(f["nominativ"]), strip_macrons(f["genitiv"])
    d, gnr, pl_only = e["deklination"], e["genus"], e.get("numerus") == "Pl"
    gpl = f.get("genitiv_pl") == "-ium"
    par = Par()
    if " " in nom:  # Mehrwortausdrücke (res publica ...)
        par.add_one("Nominativ Sg.", nom); par.add_one("Genitiv Sg.", gen)
        return par
    if nom == "domus":
        for lab, x in (("Nominativ Sg.", "domus"), ("Genitiv Sg.", ["domus", "domi"]),
                       ("Dativ Sg.", ["domui", "domo"]), ("Akkusativ Sg.", "domum"),
                       ("Ablativ Sg.", ["domo", "domu"]), ("Lokativ", "domi"),
                       ("Nominativ Pl.", "domus"), ("Genitiv Pl.", ["domorum", "domuum"]),
                       ("Dativ/Ablativ Pl.", "domibus"),
                       ("Akkusativ Pl.", ["domos", "domus"])):
            par.add_one(lab, x)
        return par
    if nom == "vis":
        for lab, x in (("Nominativ Sg.", "vis"), ("Genitiv Sg.", "vis"), ("Dativ Sg.", "vi"),
                       ("Akkusativ Sg.", "vim"), ("Ablativ Sg.", "vi")):
            par.add_one(lab, x)
        return par
    sg, pl = {}, {}
    if d == 1:
        st = gen[:-4] if pl_only else gen[:-2]
        sg = [nom, st + "ae", st + "ae", st + "am", st + "a", nom]
        pl = [st + "ae", st + "arum", st + "is", st + "as", st + "is", st + "ae"]
    elif d == 2:
        st = gen[:-4] if pl_only else gen[:-1]
        if gnr == "n":
            sg = [nom, [st + "i"], st + "o", nom, st + "o", nom]
            pl = [st + "a", st + "orum", st + "is", st + "a", st + "is", st + "a"]
        else:
            voc = [st + "e"] + ([st] if st.endswith("i") else []) if nom.endswith("us") else [nom]
            genv = [st + "i"] + ([st] if gen.endswith("ii") else [])
            sg = [nom, genv, st + "o", st + "um", st + "o", voc]
            pl = [st + "i", st + "orum", st + "is", st + "os", st + "is", st + "i"]
        if nom == "deus":
            pl = [["dei", "di", "dii"], "deorum", ["deis", "dis", "diis"], "deos", ["deis", "dis", "diis"], "dei"]
    elif d == 3:
        if pl_only:
            if gen.endswith("ium"):
                st, gpl = gen[:-3], True
            else:
                st = gen[:-2]
        else:
            st = gen[:-2]
        akk = nom if gnr == "n" else [st + "em"] + ([st + "im"] if nom.endswith("is") else [])
        abl = [st + "e"] + ([st + "i"] if nom.endswith("is") or gnr == "n" and nom.endswith(("e", "al", "ar")) else [])
        sg = [nom, st + "is", st + "i", akk, abl, nom]
        if gnr == "n":
            npl = st + ("ia" if gpl else "a")
            pl = [npl, [st + "ium"] if gpl else [st + "um"], st + "ibus", npl, st + "ibus", npl]
        else:
            pl = [st + "es", [st + "ium"] if gpl else [st + "um"], st + "ibus",
                  [st + "es"] + ([st + "is"] if gpl else []), st + "ibus", st + "es"]
    elif d == 4:
        st = gen[:-4] if pl_only else gen[:-2]
        if gnr == "n":                      # cornu, genu
            sg = [nom, st + "us", st + "u", nom, st + "u", nom]
            pl = [st + "ua", st + "uum", st + "ibus", st + "ua", st + "ibus", st + "ua"]
        else:
            sg = [nom, st + "us", st + "ui", st + "um", st + "u", nom]
            pl = [st + "us", st + "uum", st + "ibus", st + "us", st + "ibus", st + "us"]
    elif d == 5:
        st = gen[:-2]
        sg = [nom, st + "ei", st + "ei", st + "em", st + "e", nom]
        pl = [st + "es", st + "erum", st + "ebus", st + "es", st + "ebus", st + "es"]
    else:
        return par
    if pl_only:
        pl[0] = pl[5] = nom          # Nominativ/Vokativ Pl. steht so im Lemma
        for ci, x in enumerate(pl):
            par.add_one(f"{CASES[ci]} Pl.", x)
    else:
        for ci, x in enumerate(sg):
            par.add_one(f"{CASES[ci]} Sg.", x)
        if d != 5 or nom in ("res", "dies"):
            for ci, x in enumerate(pl):
                par.add_one(f"{CASES[ci]} Pl.", x)
    return par


DUO_FORMEN = [
    ("Nominativ Pl. m", "duo"), ("Nominativ Pl. f", "duae"), ("Nominativ Pl. n", "duo"),
    ("Genitiv Pl. m/n", "duorum"), ("Genitiv Pl. f", "duarum"),
    ("Dativ/Ablativ Pl.", "duobus"), ("Dativ/Ablativ Pl. f", "duabus"),
    ("Akkusativ Pl. m", ["duos", "duo"]), ("Akkusativ Pl. f", "duas"),
    ("Akkusativ Pl. n", "duo"),
]


def _adj_par(e):
    f = e["formen"]
    m, fe, n = (strip_macrons(f[k]) for k in ("m", "f", "n"))
    gen = strip_macrons(f["genitiv"]) if f.get("genitiv") else None
    lemma = e["latein"]
    par = Par()
    if norm(lemma) == "duo":
        for lab, x in DUO_FORMEN:
            par.add_one(lab, x)
        return par
    if fe.endswith("que"):                       # plerique u.ä.
        for lab, x in (("Nominativ Pl. m", m), ("Nominativ Pl. f", fe), ("Nominativ Pl. n", n)):
            par.add_one(lab, x)
    elif fe.endswith("ae") or fe.endswith("a"):
        stem = fe[:-2] if fe.endswith("ae") else fe[:-1]
        plural_given = m.endswith("i") and fe.endswith("ae")
        if plural_given:
            _adj12_rows(par, stem, stem + "us", fe, stem + "um", sg=False)
        else:
            _adj12_rows(par, stem, m, fe, n)
        _comparison_rows(par, lemma, stem, m, dritte=False)
    elif gen or fe.endswith("is"):
        stem = gen[:-2] if gen else fe[:-2]
        komparativ = m.endswith("ior")
        _adj3_rows(par, stem, m, fe, n, comparative=komparativ)
        if not komparativ:
            _comparison_rows(par, lemma, stem, m, dritte=True)
    else:
        for lab, x in (("m", m), ("f", fe), ("n", n)):
            par.add_one(lab, x)
    return par


# --------------------------------------------------------------------------
#  Hilfsfunktionen für Suche
# --------------------------------------------------------------------------

def latin_variants(latein):
    s0 = re.sub(r"\(.*?\)", " ", latein)
    parts = re.split(r"\s*/\s*|,\s*|\s*\.\.\.\s*", s0)
    out = {norm(s0)}
    for p in parts:
        if norm(p):
            out.add(norm(p))
    out.discard("")
    return out


def german_phrases(deutsch):
    out = set()
    for raw in re.split(r"[;,]", deutsch):
        raw = raw.strip()
        if not raw:
            continue
        variants = set()
        no_par = re.sub(r"\(.*?\)", " ", raw).strip()
        if no_par:
            variants.add(no_par)
        variants.add(raw.replace("(", "").replace(")", ""))
        for v in variants:
            v = re.sub(r"^(pl\.|subst\.|adj\.|m\. dopp\. akk\.|m\. \w+\.)\s*", "", v.strip(), flags=re.I)
            v = re.sub(r"^(der|die|das|ein|eine|sich|einen|einem)\s+", "", v.strip(), flags=re.I)
            v = gnorm(v)
            if v:
                out.add(v)
    return out


GER_STOP = {"der", "die", "das", "ein", "eine", "und", "oder", "von", "mit", "zu", "in", "an", "auf",
            "sich", "etw", "jdm", "jd", "pl", "sg", "subst", "adj", "akk", "dat", "abl", "gen", "vor",
            "nach", "bei", "aus", "als", "wie", "zum", "zur", "den", "dem", "des", "im"}

WORTART_ORDER = ["Substantiv", "Verb", "Adjektiv", "Pronomen", "Adverb", "Präposition", "Konjunktion",
                 "Subjunktion", "Partikel", "Interjektion", "Wendung"]


# --------------------------------------------------------------------------
#  Datenbank
# --------------------------------------------------------------------------

class VokabelBase:
    def __init__(self, path=DB_PATH):
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)["lektionen"]
        self.entries = []
        for lek, lst in raw.items():
            for e in lst:
                e["lektion"] = int(lek)
                self.entries.append(e)
        self._build()

    # ------------------------------------------------------------ Aufbau
    def _build(self):
        groups = OrderedDict()
        for e in self.entries:
            if e["wortart"] == "Verb":
                key = ("Verb", norm(e["formen"]["infinitiv"]))
            else:
                key = (e["wortart"], norm(e["latein"]))
            g = groups.setdefault(key, {"key": key, "wortart": e["wortart"], "entries": [], "lemma": e["latein"]})
            g["entries"].append(e)
        self.groups = list(groups.values())
        for i, g in enumerate(self.groups):
            g["id"] = i

        self.lemma_index = defaultdict(set)      # norm -> {group id}
        self.form_index = defaultdict(lambda: defaultdict(list))  # norm -> gid -> [labels]
        self.ger_phrase = defaultdict(set)
        self.ger_word = defaultdict(set)
        self.phrase_word = defaultdict(set)      # Wörter innerhalb von Wendungen

        for g in self.groups:
            e0 = g["entries"][0]
            wa = g["wortart"]
            # Lemma-Varianten
            variants = set()
            for e in g["entries"]:
                variants |= latin_variants(e["latein"])
            if wa == "Verb":
                _prepare_verb_group(g)
                variants |= latin_variants(g["inf"])
                g["lemma"] = strip_macrons(g["entries"][0]["latein"])
            for v in variants:
                self.lemma_index[v].add(g["id"])
            # Wendungen: einzelne Wörter zugänglich machen
            if wa == "Wendung" or (" " in norm(e0["latein"]) and wa == "Verb"):
                for e in g["entries"]:
                    for w in norm(e["latein"]).split():
                        if len(w) > 2:
                            self.phrase_word[w].add(g["id"])
            # Paradigma
            par = None
            if wa == "Verb":
                if g["conj"]:
                    par = _verb_par(g)
            elif wa == "Substantiv":
                par = _noun_par(e0)
                # gleiche Lemmata (Sol/sol) nur einmal erzeugen
            elif wa == "Adjektiv":
                par = _adj_par(e0)
            elif wa == "Pronomen":
                par = Par()
                first = norm(re.split(r"[,(/ ]", e0["latein"])[0])
                for lab, x in PRON_FORMS.get(first, []):
                    par.add_one(lab, x)
                for k, v in e0.get("formen", {}).items():
                    par.add_one(FORMEN_LABEL.get(k, k), v)
            elif e0.get("formen"):
                par = Par()
                for k, v in e0["formen"].items():
                    par.add_one(FORMEN_LABEL.get(k, k), v)
            g["par"] = par
            if par:
                for label, person, alts in par.rows:
                    full = label + (", " + person if person else "")
                    for a in alts:
                        na = norm(a)
                        if na:
                            lst = self.form_index[na][g["id"]]
                            if full not in lst:
                                lst.append(full)
            # Deutsch
            for e in g["entries"]:
                phrases = german_phrases(e["deutsch"])
                for p in phrases:
                    self.ger_phrase[p].add(g["id"])
                    for w in p.split():
                        if len(w) > 2 and w not in GER_STOP:
                            self.ger_word[w].add(g["id"])

        # Wendungen ueber ihre Bestandteile auffindbar machen: jedes Wort einer
        # Wendung wird (auch in gebeugter Form) seiner Vokabelgruppe zugeordnet,
        # damit "debeo" die Wendung "gratiam debere" mitliefert.
        self.phrase_of_group = defaultdict(set)
        for g in self.groups:
            for e in g["entries"]:
                words = norm(e["latein"]).split()
                if len(words) < 2:
                    continue
                for w in words:
                    if len(w) <= 2:
                        continue
                    for other in set(self.lemma_index.get(w, ())) | set(self.form_index.get(w, {})):
                        if other != g["id"]:
                            self.phrase_of_group[other].add(g["id"])

    # ------------------------------------------------------------ Suche
    def _lookup_latin_token(self, tok):
        """Liefert dict gid -> {'lemma': bool, 'labels': [...], 'enclitic': str|None}"""
        hits = {}
        nt = norm(tok)
        if not nt:
            return hits
        for gid in self.lemma_index.get(nt, ()):
            hits.setdefault(gid, {"lemma": False, "labels": [], "enclitic": None})["lemma"] = True
        for gid, labels in self.form_index.get(nt, {}).items():
            h = hits.setdefault(gid, {"lemma": False, "labels": [], "enclitic": None})
            for l in labels:
                if l not in h["labels"]:
                    h["labels"].append(l)
        return hits

    def search(self, query):
        """Suche nach einem Wort (oder einer Wortgruppe).  Gibt ein dict zurück:
           {'latein': {gid: info}, 'deutsch': [(gid, 'genau'|'wort')], 'wendungen': [gid],
            'vorschlaege': [...]}"""
        q = query.strip()
        result = {"query": q, "latein": {}, "deutsch": [], "wendungen": [],
                  "woerter": [], "vorschlaege": []}
        if not q:
            return result
        # 1) Ganze Eingabe (auch Wendungen wie "res publica")
        result["latein"] = self._lookup_latin_token(q)
        if not result["latein"]:
            # Lemmata mit Zusatz in Klammern ("in (Abl.)", "aedes (Pl.)")
            for v in latin_variants(q):
                for gid, h in self._lookup_latin_token(v).items():
                    result["latein"].setdefault(gid, h)
        # 2) Enklitika (-que, -ne, -ve)
        if not result["latein"] and " " not in q:
            nq = norm(q)
            for enc in ("que", "ne", "ve"):
                if nq.endswith(enc) and len(nq) > len(enc) + 2:
                    sub = self._lookup_latin_token(nq[: -len(enc)])
                    for gid, h in sub.items():
                        h["enclitic"] = "-" + enc
                    if sub:
                        result["latein"] = sub
                        break
        # 3) Deutsch
        gq = gnorm(q)
        seen = set()
        for gid in sorted(self.ger_phrase.get(gq, ())):
            result["deutsch"].append((gid, "genau")); seen.add(gid)
        if gq and " " not in gq:
            for gid in sorted(self.ger_word.get(gq, ())):
                if gid not in seen:
                    result["deutsch"].append((gid, "wort")); seen.add(gid)
        # 4) Wendungen, in denen das Wort vorkommt – auch in gebeugter Form
        nq = norm(q)
        wend = set()
        if nq and " " not in nq:
            wend |= set(self.phrase_word.get(nq, ()))
        for gid in result["latein"]:
            wend |= self.phrase_of_group.get(gid, set())
        result["wendungen"] = sorted(w for w in wend if w not in result["latein"])
        # 5) Mehrteilige Eingabe ("laudatus est", "castra posuerunt") Wort für Wort
        if not result["latein"] and len(nq.split()) > 1:
            for tok in nq.split():
                hits = self._lookup_latin_token(tok)
                if hits:
                    result["woerter"].append((tok, hits))
                    for gid in hits:
                        wend |= self.phrase_of_group.get(gid, set())
            result["wendungen"] = sorted(wend)
        # 6) Vorschläge
        if not result["latein"] and not result["deutsch"] and not result["woerter"]:
            result["vorschlaege"] = self.suggest(q)
        return result

    # ------------------------------------------------------------ Vorschläge
    def suggest(self, query, n=6, cutoff=0.6):
        qn, gq = norm(query), gnorm(query)
        cand = {}   # gid -> (score, text)

        def consider(pool, q, describe, min_score=cutoff):
            if not q:
                return
            sm = SequenceMatcher()
            sm.set_seq2(q)
            for key in pool:
                if abs(len(key) - len(q)) > 3:
                    continue
                sm.set_seq1(key)
                if sm.real_quick_ratio() < min_score or sm.quick_ratio() < min_score:
                    continue
                r = sm.ratio()
                if r >= min_score:
                    describe(key, r)

        def rec(gid, r, text):
            if gid not in cand or cand[gid][0] < r:
                cand[gid] = (r, text)

        def d_lemma(key, r):
            for gid in self.lemma_index[key]:
                g = self.groups[gid]
                rec(gid, r, f"{g['lemma']}  –  {g['entries'][0]['deutsch']}")

        def d_ger(key, r):
            for gid in self.ger_phrase[key]:
                g = self.groups[gid]
                rec(gid, r * 0.98, f"{g['lemma']}  –  {g['entries'][0]['deutsch']}   (deutsch: {key})")

        def d_gerw(key, r):
            for gid in self.ger_word[key]:
                g = self.groups[gid]
                rec(gid, r * 0.95, f"{g['lemma']}  –  {g['entries'][0]['deutsch']}   (deutsch: {key})")

        consider(self.lemma_index.keys(), qn, d_lemma)
        consider(self.ger_phrase.keys(), gq, d_ger)
        consider(self.ger_word.keys(), gq, d_gerw)
        # Formen (nur wenn das Lemma-Ergebnis dünn ist)
        if len(cand) < n and qn:
            pool = [k for k in self.form_index if k and k[0] == qn[0]]

            def d_form(key, r):
                for gid, labels in self.form_index[key].items():
                    g = self.groups[gid]
                    rec(gid, r * 0.97, f"{key}  (Form von {g['lemma']}: {labels[0]})  –  {g['entries'][0]['deutsch']}")
            consider(pool, qn, d_form, min_score=max(cutoff, 0.72))
        best = sorted(cand.items(), key=lambda kv: -kv[1][0])[:n]
        return [(gid, sc, txt) for gid, (sc, txt) in best]

    # ------------------------------------------------------------ Ausgabe
    def format_entry(self, e, indent="    "):
        lines = [f"{indent}[Lektion {e['lektion']}]  {e['deutsch']}"]
        parts = []
        for k, v in e.get("formen", {}).items():
            parts.append(f"{FORMEN_LABEL.get(k, k)}: {v}")
        if parts:
            lines.append(f"{indent}   " + "  |  ".join(parts))
        extra = []
        if e.get("genus"):
            extra.append(f"Genus: {e['genus']}")
        if e.get("deklination"):
            extra.append(f"Deklination: {e['deklination']}")
        if e.get("numerus"):
            extra.append(f"nur {e['numerus']}")
        if e.get("kasus"):
            extra.append(f"Kasus: {e['kasus']}")
        if extra:
            lines.append(f"{indent}   " + "  |  ".join(extra))
        return "\n".join(lines)

    def format_group(self, gid, info=None, german_match=None):
        g = self.groups[gid]
        head = f"► {g['lemma']}   ({g['wortart']}"
        if g["wortart"] == "Verb" and g.get("conj"):
            head += f", {CONJ_NAMES[g['conj']]}"
        head += ")"
        lines = [head]
        if info:
            if info.get("enclitic"):
                lines.append(f"    Angehängtes {info['enclitic']} erkannt (= „und“ / Fragepartikel / „oder“)")
            if info["labels"]:
                shown = info["labels"] if len(info["labels"]) <= 6 else info["labels"][:6] + ["…"]
                lines.append("    Bestimmung: " + "  /  ".join(shown))
            elif info["lemma"]:
                lines.append("    Grundform")
        if german_match:
            lines.append("    (Treffer über die deutsche Bedeutung)")
        for e in sorted(g["entries"], key=lambda x: x["lektion"]):
            lines.append(self.format_entry(e))
        return "\n".join(lines)

    def format_paradigm(self, gid):
        g = self.groups[gid]
        par = g.get("par")
        if not par or not par.rows:
            return f"► {g['lemma']}: keine Formentabelle vorhanden."
        grouped = OrderedDict()
        for label, person, alts in par.rows:
            grouped.setdefault(label, []).append("/".join(alts))
        out = [f"► Formen von {g['lemma']}"]
        for label, forms in grouped.items():
            out.append(f"    {label}: " + ", ".join(forms))
        return "\n".join(out)

    def format_result(self, res):
        out = []
        lat = res["latein"]
        order = sorted(lat.items(), key=lambda kv: (not kv[1]["lemma"],
                       WORTART_ORDER.index(self.groups[kv[0]]["wortart"]) if self.groups[kv[0]]["wortart"] in WORTART_ORDER else 99))
        if order:
            out.append("── Lateinisch ──")
            for gid, info in order:
                out.append(self.format_group(gid, info))
        if res["deutsch"]:
            out.append("── Deutsche Bedeutung ──")
            shown = 0
            for gid, typ in res["deutsch"]:
                if gid in lat:
                    continue
                out.append(self.format_group(gid, None, german_match=True))
                shown += 1
                if shown >= 12:
                    out.append("    … (weitere Treffer nicht angezeigt)")
                    break
        if res["woerter"]:
            out.append("── Wort für Wort ──")
            for tok, hits in res["woerter"]:
                out.append(f"  ▸ {tok}")
                for gid, info in hits.items():
                    for line in self.format_group(gid, info).splitlines():
                        out.append("  " + line)
        if res["wendungen"]:
            out.append("── Kommt außerdem in diesen Wendungen vor ──")
            for gid in res["wendungen"][:6]:
                g = self.groups[gid]
                out.append(f"    {g['lemma']}  –  {g['entries'][0]['deutsch']}  [Lektion {g['entries'][0]['lektion']}]")
        if not out:
            out.append(f"Keine Vokabel zu „{res['query']}“ gefunden.")
            if res["vorschlaege"]:
                out.append("Meintest du vielleicht:")
                for gid, sc, txt in res["vorschlaege"]:
                    out.append(f"    • {txt}   [{int(sc * 100)} %]")
            else:
                out.append("Auch keine ähnlichen Wörter gefunden.")
        return "\n".join(out)

# --------------------------------------------------------------------------
#  Ausgabe auf der Konsole
# --------------------------------------------------------------------------

def setup_console():
    """Windows-Konsolen laufen oft auf cp1252 – dort lässt sich „servī" nicht
    drucken.  Erst auf UTF-8 umstellen, damit print() nicht abbricht."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def emit(text=""):
    """print(), das auch auf einer Konsole ohne UTF-8 nicht abstürzt."""
    try:
        print(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(strip_macrons(str(text)).encode(enc, "replace").decode(enc))


def ask(prompt):
    """input(), das bei Strg+C / Strg+D sauber None zurückgibt."""
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        emit()
        return None


# --------------------------------------------------------------------------
#  Kommandozeilen-Programm
# --------------------------------------------------------------------------

HILFE = """
Einfach ein Wort eingeben – lateinisch (auch gebeugt) oder deutsch.
Beispiele:  rogaverunt   ·   altissimus   ·   castra posuerunt   ·   Sklave

Befehle:
  :formen <wort>     alle Formen einer Vokabel anzeigen (Konjugation/Deklination)
  :lektion <nr>      alle Vokabeln einer Lektion auflisten
  :quiz              das Vokabelquiz starten
  :hilfe             diese Übersicht
  :ende              Programm beenden
"""


def resolve_groups(db, wort):
    """Wort -> Liste von Gruppen-IDs (Grundform bevorzugt, sonst über Formen)."""
    res = db.search(wort)
    gids = [gid for gid, info in res["latein"].items() if info["lemma"]]
    if not gids:
        gids = list(res["latein"].keys())
    if not gids:
        gids = [gid for gid, _typ in res["deutsch"]]
    return gids


def cmd_formen(db, wort):
    gids = resolve_groups(db, wort)
    if not gids:
        emit(f"„{wort}“ nicht gefunden.")
        vor = db.suggest(wort)
        if vor:
            emit("Meintest du vielleicht:")
            for _gid, sc, txt in vor:
                emit(f"    • {txt}   [{int(sc * 100)} %]")
        return
    for gid in gids[:3]:
        emit(db.format_paradigm(gid))
        emit()


def cmd_lektion(db, arg):
    try:
        nr = int(arg)
    except ValueError:
        emit("Bitte eine Lektionsnummer angeben, z. B.  :lektion 7")
        return
    eintraege = [e for e in db.entries if e["lektion"] == nr]
    if not eintraege:
        vorhanden = sorted({e["lektion"] for e in db.entries})
        emit(f"Lektion {nr} gibt es nicht.  Vorhanden: {vorhanden[0]}–{vorhanden[-1]}")
        return
    emit(f"── Lektion {nr} ({len(eintraege)} Vokabeln) ──")
    for e in sorted(eintraege, key=lambda x: (WORTART_ORDER.index(x["wortart"])
                                              if x["wortart"] in WORTART_ORDER else 99,
                                              norm(x["latein"]))):
        emit(f"    {e['latein']:<28} {e['deutsch']}")


def repl(db):
    emit("=== Lateinische Vokabelsuche ===")
    emit(f"{len(db.entries)} Vokabeln, {len(db.form_index)} erkannte Formen.")
    emit("„:hilfe“ zeigt alle Befehle, „:ende“ beendet das Programm.")
    while True:
        zeile = ask("\nSuche> ")
        if zeile is None:
            break
        zeile = zeile.strip()
        if not zeile:
            continue
        if zeile.startswith(":"):
            teile = zeile[1:].split(None, 1)
            befehl = teile[0].lower() if teile else ""
            arg = teile[1].strip() if len(teile) > 1 else ""
            if befehl in ("ende", "quit", "exit", "q"):
                break
            if befehl in ("hilfe", "help", "h", "?"):
                emit(HILFE)
            elif befehl in ("formen", "form"):
                cmd_formen(db, arg) if arg else emit("Beispiel:  :formen rogare")
            elif befehl in ("lektion", "lek", "l"):
                cmd_lektion(db, arg)
            elif befehl == "quiz":
                try:
                    import vokabel_search
                    vokabel_search.start_quiz(db)
                except Exception as ex:
                    emit(f"Das Quiz lässt sich nicht starten: {type(ex).__name__}: {ex}")
            else:
                emit(f"Unbekannter Befehl „:{befehl}“.  „:hilfe“ zeigt alle Befehle.")
            continue
        res = db.search(zeile)
        emit(db.format_result(res))
        treffer = list(res["latein"])
        if len(treffer) == 1 and db.groups[treffer[0]].get("par"):
            emit(f"    → alle Formen:  :formen {db.groups[treffer[0]]['lemma']}")
    emit("Bis bald!")


def main(argv=None):
    setup_console()
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        db = VokabelBase()
    except FileNotFoundError:
        emit(f"Die Vokabeldatei wurde nicht gefunden: {DB_PATH}")
        return 1
    except (json.JSONDecodeError, KeyError) as ex:
        emit(f"Die Vokabeldatei ist beschädigt: {ex}")
        return 1
    if argv:
        if argv[0] in ("-f", "--formen"):
            cmd_formen(db, " ".join(argv[1:]))
        else:
            emit(db.format_result(db.search(" ".join(argv))))
        return 0
    repl(db)
    return 0


if __name__ == "__main__":
    sys.exit(main())
