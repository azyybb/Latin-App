"""
tabellen.py  -  ganze Formtabellen abfragen (Quiz-Modus „Tabellen“)
===================================================================
Vor allem die unregelmäßigen Tabellen, die man auswendig lernen muss:
Pronomen (is, qui, hic, ille ...), esse/posse/velle/nolle/ire/ferre,
besondere Substantive und die Steigerung.

Die Tabellen stehen hier von Hand - die automatisch erzeugten Paradigmen
fassen gleiche Formen zusammen ("Ablativ Sg. m/n") und taugen nicht als
Abfrageraster.  Jede Tabelle und jede Spalte hat eine Lektion: abgefragt
wird nur, was bis zur gewählten Lektion drankam.

    py -3 programm/tabellen.py      prüft alle Formen gegen die Formerkennung
"""

import random
import sys

from bettervokable_search import norm

KASUS = ["Nominativ", "Genitiv", "Dativ", "Akkusativ", "Ablativ"]
PERSONEN = ["1. Sg.", "2. Sg.", "3. Sg.", "1. Pl.", "2. Pl.", "3. Pl."]

# In welcher Lektion die Zeiten drankommen (wie in vokabel_search.FORM_LEKTION)
ZEIT_LEKTION = {"Präsens": 1, "Imperfekt": 8, "Perfekt": 8, "Plusquamperfekt": 10, "Futur I": 11}


def _zellen(text):
    """"is | ea | id" -> [["is"], ["ea"], ["id"]];  "ei/ii" = zwei richtige Formen,
    "–" = gibt es nicht."""
    ergebnis = []
    for teil in text.split("|"):
        teil = teil.strip()
        ergebnis.append(None if teil in ("–", "-", "") else [f.strip() for f in teil.split("/")])
    return ergebnis


def pronomen(schluessel, titel, lektion, zeilen, hinweis=""):
    """zeilen: 10 Zeilen "m | f | n" - Nom. Gen. Dat. Akk. Abl. im Sg., dann Pl."""
    assert len(zeilen) == 10, schluessel
    namen = [f"{k} Sg." for k in KASUS] + [f"{k} Pl." for k in KASUS]
    return {"key": schluessel, "titel": titel, "lektion": lektion, "art": "Pronomen",
            "hinweis": hinweis, "spalten": [("m", lektion), ("f", lektion), ("n", lektion)],
            "zeilen": namen, "formen": [_zellen(z) for z in zeilen]}


def verb(schluessel, titel, lektion, zeiten, hinweis=""):
    """zeiten: {"Präsens": "sum es est sumus estis sunt", ...}  ("non vis" als
    "non_vis" schreiben; mehrere richtige Formen mit "/")."""
    spalten, spalten_formen = [], []
    for zeit, formen in zeiten.items():
        spalten.append((zeit, max(lektion, ZEIT_LEKTION[zeit])))
        teile = formen.split()
        assert len(teile) == 6, (schluessel, zeit)
        spalten_formen.append([[f.replace("_", " ") for f in t.split("/")] for t in teile])
    formen = [[spalten_formen[s][p] for s in range(len(spalten))] for p in range(6)]
    return {"key": schluessel, "titel": titel, "lektion": lektion, "art": "Verb",
            "hinweis": hinweis, "spalten": spalten, "zeilen": PERSONEN, "formen": formen}


def nomen(schluessel, titel, lektion, zeilen, hinweis=""):
    """zeilen: 5 Zeilen "Singular | Plural"."""
    assert len(zeilen) == 5, schluessel
    return {"key": schluessel, "titel": titel, "lektion": lektion, "art": "Substantiv",
            "hinweis": hinweis, "spalten": [("Singular", lektion), ("Plural", lektion)],
            "zeilen": list(KASUS), "formen": [_zellen(z) for z in zeilen]}


def steigerung(schluessel, titel, lektion, zeilen, hinweis=""):
    """zeilen: "Positiv | Komparativ | Superlativ" (Nom. Sg. m); der Positiv ist vorgegeben."""
    return {"key": schluessel, "titel": titel, "lektion": lektion, "art": "Steigerung",
            "hinweis": hinweis,
            "spalten": [("Positiv", lektion), ("Komparativ", lektion), ("Superlativ", lektion)],
            "zeilen": [z.split("|")[0].strip() for z in zeilen],
            "formen": [_zellen(z) for z in zeilen], "vorgegeben": [0]}


TABELLEN = [
    # ---------------------------------------------------------- Pronomen
    {   # fünf Spalten statt m/f/n, das Reflexivpronomen erst ab L12
        "key": "personal", "titel": "Personalpronomen: ego, tu, nos, vos", "lektion": 9,
        "art": "Pronomen", "zeilen": KASUS,
        "spalten": [("ich", 9), ("du", 9), ("wir", 9), ("ihr", 9), ("sich (reflexiv)", 12)],
        "hinweis": "Mit cum verschmilzt der Ablativ: mēcum, tēcum, nōbīscum, vōbīscum, sēcum. "
                   "Das Reflexivpronomen hat keinen Nominativ.",
        "formen": [_zellen(z) for z in [
            "ego | tu | nos | vos | –",
            "mei | tui | nostri/nostrum | vestri/vestrum | sui",
            "mihi | tibi | nobis | vobis | sibi",
            "me | te | nos | vos | se",
            "me | te | nobis | vobis | se",
        ]]},
    pronomen("is", "is, ea, id – dieser; er, sie, es", 10, [
        "is | ea | id",
        "eius | eius | eius",
        "ei | ei | ei",
        "eum | eam | id",
        "eo | ea | eo",
        "ei/ii | eae | ea",
        "eorum | earum | eorum",
        "eis/iis | eis/iis | eis/iis",
        "eos | eas | ea",
        "eis/iis | eis/iis | eis/iis",
    ], "Genitiv und Dativ Sg. sind für alle drei Geschlechter gleich: eius, ei."),
    pronomen("qui", "qui, quae, quod – Relativpronomen", 11, [
        "qui | quae | quod",
        "cuius | cuius | cuius",
        "cui | cui | cui",
        "quem | quam | quod",
        "quo | qua | quo",
        "qui | quae | quae",
        "quorum | quarum | quorum",
        "quibus | quibus | quibus",
        "quos | quas | quae",
        "quibus | quibus | quibus",
    ], "quae steht viermal: Nom. Sg. f, Nom. Pl. f, Nom./Akk. Pl. n."),
    pronomen("hic", "hic, haec, hoc – dieser (hier)", 17, [
        "hic | haec | hoc",
        "huius | huius | huius",
        "huic | huic | huic",
        "hunc | hanc | hoc",
        "hoc | hac | hoc",
        "hi | hae | haec",
        "horum | harum | horum",
        "his | his | his",
        "hos | has | haec",
        "his | his | his",
    ], "Achtung: haec ist Nom. Sg. f UND Nom./Akk. Pl. n."),
    pronomen("ille", "ille, illa, illud – jener", 17, [
        "ille | illa | illud",
        "illius | illius | illius",
        "illi | illi | illi",
        "illum | illam | illud",
        "illo | illa | illo",
        "illi | illae | illa",
        "illorum | illarum | illorum",
        "illis | illis | illis",
        "illos | illas | illa",
        "illis | illis | illis",
    ], "Genitiv Sg. auf -ius, Dativ Sg. auf -i – sonst wie magnus, a, um."),
    pronomen("iste", "iste, ista, istud – dieser (da)", 18, [
        "iste | ista | istud",
        "istius | istius | istius",
        "isti | isti | isti",
        "istum | istam | istud",
        "isto | ista | isto",
        "isti | istae | ista",
        "istorum | istarum | istorum",
        "istis | istis | istis",
        "istos | istas | ista",
        "istis | istis | istis",
    ], "Wird genau wie ille gebildet."),
    pronomen("idem", "idem, eadem, idem – derselbe", 18, [
        "idem | eadem | idem",
        "eiusdem | eiusdem | eiusdem",
        "eidem | eidem | eidem",
        "eundem | eandem | idem",
        "eodem | eadem | eodem",
        "eidem/iidem/idem | eaedem | eadem",
        "eorundem | earundem | eorundem",
        "eisdem/iisdem/isdem | eisdem/iisdem/isdem | eisdem/iisdem/isdem",
        "eosdem | easdem | eadem",
        "eisdem/iisdem/isdem | eisdem/iisdem/isdem | eisdem/iisdem/isdem",
    ], "is, ea, id + -dem; vor -dem wird m zu n: eundem, eandem, eorundem, earundem."),

    # ---------------------------------------------------------- Verben
    verb("esse", "esse – sein", 1, {
        "Präsens": "sum es est sumus estis sunt",
        "Imperfekt": "eram eras erat eramus eratis erant",
        "Perfekt": "fui fuisti fuit fuimus fuistis fuerunt/fuere",
        "Plusquamperfekt": "fueram fueras fuerat fueramus fueratis fuerant",
        "Futur I": "ero eris erit erimus eritis erunt",
    }, "Futur: ero, eris, erit … – Achtung, 3. Pl. erunt (nicht erint)."),
    verb("posse", "posse – können", 7, {
        "Präsens": "possum potes potest possumus potestis possunt",
        "Imperfekt": "poteram poteras poterat poteramus poteratis poterant",
        "Perfekt": "potui potuisti potuit potuimus potuistis potuerunt/potuere",
        "Plusquamperfekt": "potueram potueras potuerat potueramus potueratis potuerant",
        "Futur I": "potero poteris poterit poterimus poteritis poterunt",
    }, "pot- + Formen von esse; vor s wird t zu s: possum, possumus, possunt."),
    verb("velle", "velle – wollen", 4, {
        "Präsens": "volo vis vult volumus vultis volunt",
        "Imperfekt": "volebam volebas volebat volebamus volebatis volebant",
        "Perfekt": "volui voluisti voluit voluimus voluistis voluerunt/voluere",
        "Plusquamperfekt": "volueram volueras voluerat volueramus volueratis voluerant",
        "Futur I": "volam voles volet volemus voletis volent",
    }, "Präsens unregelmäßig: vis, vult, vultis; Futur wie die e-Konjugation: volam, voles."),
    verb("nolle", "nolle – nicht wollen", 4, {
        "Präsens": "nolo non_vis non_vult nolumus non_vultis nolunt",
        "Imperfekt": "nolebam nolebas nolebat nolebamus nolebatis nolebant",
        "Perfekt": "nolui noluisti noluit noluimus noluistis noluerunt/noluere",
        "Plusquamperfekt": "nolueram nolueras noluerat nolueramus nolueratis noluerant",
        "Futur I": "nolam noles nolet nolemus noletis nolent",
    }, "non + velle: nōn vīs, nōn vult, nōn vultis werden getrennt geschrieben."),
    verb("ire", "ire – gehen", 12, {
        "Präsens": "eo is it imus itis eunt",
        "Imperfekt": "ibam ibas ibat ibamus ibatis ibant",
        "Perfekt": "ii isti/iisti iit iimus istis/iistis ierunt/iere",
        "Plusquamperfekt": "ieram ieras ierat ieramus ieratis ierant",
        "Futur I": "ibo ibis ibit ibimus ibitis ibunt",
    }, "Vor a, o, u wird i zu e: eo, eunt. Futur mit -b-: ibo, ibis (wie die a-Konjugation)."),
    verb("ferre", "ferre – tragen, bringen", 16, {
        "Präsens": "fero fers fert ferimus fertis ferunt",
        "Imperfekt": "ferebam ferebas ferebat ferebamus ferebatis ferebant",
        "Perfekt": "tuli tulisti tulit tulimus tulistis tulerunt/tulere",
        "Plusquamperfekt": "tuleram tuleras tulerat tuleramus tuleratis tulerant",
        "Futur I": "feram feres feret feremus feretis ferent",
    }, "Stammformen ferō, ferre, tulī, lātum. Im Präsens fehlt oft der Bindevokal: fers, fert, fertis."),

    # ---------------------------------------------------------- Substantive
    nomen("iuppiter", "Iuppiter – Jupiter", 5, [
        "Iuppiter | –", "Iovis | –", "Iovi | –", "Iovem | –", "Iove | –",
    ], "Ab dem Genitiv ganz anderer Stamm: Iov-."),
    nomen("vis", "vis, vires – Kraft, Gewalt; Pl. Kräfte, Streitkräfte", 12, [
        "vis | vires", "– | virium", "– | viribus", "vim | vires", "vi | viribus",
    ], "Im Singular nur vīs, vim, vī; der Plural vīrēs wird wie ein i-Stamm dekliniert."),
    nomen("res", "res – Sache (e-Deklination)", 13, [
        "res | res", "rei | rerum", "rei | rebus", "rem | res", "re | rebus",
    ], "Genauso: diēs, spēs (Pl. selten), fidēs."),
    nomen("domus", "domus – Haus", 17, [
        "domus | domus", "domus | domuum/domorum", "domui | domibus",
        "domum | domos/domus", "domo | domibus",
    ], "Mischt u- und o-Deklination: Abl. Sg. domō, Akk. Pl. domōs. Merke auch: domī (zu Hause), domum (nach Hause)."),

    # ---------------------------------------------------------- Steigerung
    steigerung("steigerung_unregel", "Steigerung: unregelmäßig (Zusatz)", 20, [
        "bonus | melior | optimus",
        "malus | peior | pessimus",
        "magnus | maior | maximus",
        "parvus | minor | minimus",
        "multi | plures | plurimi",
    ], "Nur der Nominativ Sg. m (bei multi der Plural). Komparativ: melior, melius (n)."),
    steigerung("steigerung_regel", "Steigerung: regelmäßig (Zusatz)", 20, [
        "laetus | laetior | laetissimus",
        "fortis | fortior | fortissimus",
        "clarus | clarior | clarissimus",
        "pulcher | pulchrior | pulcherrimus",
        "acer | acrior | acerrimus",
        "facilis | facilior | facillimus",
        "celer | celerior | celerrimus",
    ], "Komparativ -ior, Superlativ -issimus. Adjektive auf -er: -errimus; facilis, similis, difficilis: -illimus."),
]
TABELLEN = {t["key"]: t for t in TABELLEN}


# --------------------------------------------------------------------------
#  Abfrage
# --------------------------------------------------------------------------

def _spalten(t, bis):
    return [i for i, (_n, l) in enumerate(t["spalten"]) if l <= bis]


def verfuegbar(bis):
    """Tabellen, die bis zu dieser Lektion drankamen: [(key, titel, lektion)]"""
    return sorted(((k, t["titel"], t["lektion"]) for k, t in TABELLEN.items()
                   if t["lektion"] <= bis), key=lambda x: x[2])


def aufbauen(key, bis, luecken=False):
    """Abfrageraster ohne Lösungen (außer vorgegebenen Feldern)."""
    t = TABELLEN[key]
    spalten = _spalten(t, bis)
    zellen = [(r, c) for r in range(len(t["zeilen"])) for c in spalten
              if t["formen"][r][c] is not None]
    vorgabe = {(r, c) for r, c in zellen if c in t.get("vorgegeben", ())}
    if luecken:
        frei = [z for z in zellen if z not in vorgabe]
        vorgabe |= set(random.sample(frei, len(frei) // 2))
    zeilen = []
    for r, name in enumerate(t["zeilen"]):
        reihe = []
        for c in spalten:
            formen = t["formen"][r][c]
            if formen is None:
                reihe.append(None)
            elif (r, c) in vorgabe:
                reihe.append({"id": f"{r}-{c}", "vorgabe": " / ".join(formen)})
            else:
                reihe.append({"id": f"{r}-{c}"})
        zeilen.append({"label": name, "zellen": reihe})
    return {"key": key, "titel": t["titel"], "art": t["art"], "hinweis": t["hinweis"],
            "spalten": [t["spalten"][c][0] for c in spalten], "zeilen": zeilen,
            "zusatz": t["lektion"] > 20 or "Zusatz" in t["titel"]}


def _gleich(antwort, formen):
    a = " ".join(norm(antwort).split())
    return any(a == " ".join(norm(f).split()) for f in formen)


def pruefen(key, antworten):
    """antworten: {"r-c": "Eingabe"} -> {"felder": {id: {ok, loesung}}, "richtig", "gesamt"}"""
    t = TABELLEN[key]
    felder, richtig = {}, 0
    for zid, antwort in antworten.items():
        try:
            r, c = (int(x) for x in zid.split("-"))
            formen = t["formen"][r][c]
        except (ValueError, IndexError):
            continue
        if formen is None:
            continue
        ok = _gleich(str(antwort), formen)
        richtig += ok
        felder[zid] = {"ok": ok, "loesung": " / ".join(formen)}
    return {"felder": felder, "richtig": richtig, "gesamt": len(felder)}


# --------------------------------------------------------------------------
#  Gegenprobe mit der Formerkennung
# --------------------------------------------------------------------------

def main():
    from bettervokable_search import VokabelBase
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    db = VokabelBase()
    unbekannt = 0
    for t in TABELLEN.values():
        fehlt = []
        for r, reihe in enumerate(t["formen"]):
            for c, formen in enumerate(reihe):
                for f in formen or []:
                    for teil in f.split():
                        if teil == "non":
                            continue
                        if not db.search(teil)["latein"]:
                            fehlt.append(f"{t['zeilen'][r]}/{t['spalten'][c][0]}: {f}")
        unbekannt += len(fehlt)
        print(f"{t['key']:20} L{t['lektion']:<3} {len(fehlt)} unbekannt"
              + ("" if not fehlt else "  –  " + ", ".join(fehlt)))
    print(f"{len(TABELLEN)} Tabellen; {unbekannt} Formen kennt die Formerkennung nicht "
          f"(bei Steigerung/Zusatz normal).")


if __name__ == "__main__":
    main()
