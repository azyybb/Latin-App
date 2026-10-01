"""
vokabel_gui.py  -  Fenster fuer Vokabelsuche und Quiz
=====================================================
Benutzt nur tkinter.  Das gehoert zu Python dazu, es ist nichts zu installieren.

Start:   py -3 vokabel_gui.py

Die Suche und die Antwortpruefung kommen unveraendert aus
bettervokable_search.py und vokabel_search.py - dieses Modul ist nur
die Oberflaeche dazu.
"""

import random
import re
import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk

import fehler_datenbank as FD
import grammatik as GR
import pfade

try:                      # Pillow zeigt die Buchseiten an; fehlt es, geht der Rest weiter
    from PIL import Image, ImageTk
except ImportError:
    Image = ImageTk = None
import vokabel_search as quiz
from bettervokable_search import (
    CONJ_NAMES, DB_PATH, FORMEN_LABEL, WORTART_ORDER, VokabelBase, norm,
)

# --------------------------------------------------------------------------
#  Farben und Schrift
# --------------------------------------------------------------------------
FLAECHE = "#f6f7f9"        # Fensterhintergrund
KARTE = "#ffffff"          # Eingabefelder, Listen, Textflächen
RAND = "#dfe3e8"           # feine Trennlinien
RAND_STARK = "#c4cad1"
TEXT = "#1f2328"
GRAU = "#5b636c"           # Nebentexte
BLAU = "#2563eb"           # Akzent
BLAU_HELL = "#eef3ff"
GRUEN = "#137333"
ROT = "#c5221f"
BLASS = "#c3c8ce"          # für den Schriftzug unten rechts

SCHRIFT = "Segoe UI"
MONO = "Consolas"


# --------------------------------------------------------------------------
#  Skalierung
# --------------------------------------------------------------------------
#  Zwei Dinge machen die Oberfläche sonst winzig:
#
#  1. Ein 4K-Bildschirm.  Windows vergrößert normalerweise selbst, aber das
#     schalten wir ab (dpi_beachten), damit die Schrift scharf bleibt - also
#     müssen wir selbst vergrößern.  Das macht EINHEIT.
#  2. Ein großes Fenster.  Schrift und Abstände in fester Pixelgröße wirken
#     im Vollbild verloren.  Deshalb wächst alles mit der Fenstergröße mit -
#     das macht FAKTOR.
#
#  Schriftgrößen stehen in Punkt; Tk rechnet die über "tk scaling" schon in
#  DPI um, sie brauchen darum nur den FAKTOR.  Pixelmaße (Abstände, Umbruch-
#  breiten, Zeilenhöhen) brauchen beides: px() = Einheit * Faktor.
REF_BREITE = 900           # Fenstergröße, bei der der Faktor 1.0 ist
REF_HOEHE = 680
FAKTOR_MIN = 1.0
FAKTOR_MAX = 2.2

_einheit = 1.0
_faktor = 1.0
_schriften = {}            # (Familie, Grundgröße, Stil) -> tkfont.Font
_masse = []                # [(Widget, {Option: Grundwert})]
_horcher = []              # Rückrufe nach dem Umskalieren


def einheit_bestimmen(fenster):
    """Wie viele echte Pixel ein Design-Pixel wert ist (1.5 bei 150 %)."""
    global _einheit
    try:
        _einheit = max(1.0, fenster.winfo_fpixels("1i") / 96.0)
    except Exception:
        _einheit = 1.0
    return _einheit


def px(wert):
    """Pixelmaß: wächst mit Bildschirmauflösung und Fenstergröße."""
    return max(1, int(round(wert * _einheit * _faktor)))


def dp(wert):
    """Pixelmaß nur für die Bildschirmauflösung - unabhängig vom Fenster.
    Für Fenstergrößen selbst, die ja den Faktor erst bestimmen."""
    return max(1, int(round(wert * _einheit)))


def faktor():
    return _faktor


def schrift(groesse, stil="", familie=SCHRIFT):
    """Benannte Schrift in der Grundgröße 'groesse'.  Benannt heißt: ändert
    sich später der Faktor, wachsen alle Beschriftungen von selbst mit."""
    schluessel = (familie, groesse, stil)
    vorhanden = _schriften.get(schluessel)
    if vorhanden is None:
        vorhanden = tkfont.Font(family=familie, size=max(6, round(groesse * _faktor)),
                                weight="bold" if "bold" in stil else "normal",
                                slant="italic" if "italic" in stil else "roman")
        _schriften[schluessel] = vorhanden
    return vorhanden


def faktor_fuer(breite, hoehe):
    """Der Faktor, der zu einem Fenster dieser Größe passt.

    Gerechnet wird in Design-Pixeln, also ohne die Bildschirmauflösung - sonst
    würde bei 150 % doppelt vergrößert.  Der kleinere der beiden Werte gewinnt,
    damit der Inhalt in jeder Richtung hineinpasst."""
    b = breite / _einheit / REF_BREITE
    h = hoehe / _einheit / REF_HOEHE
    return max(FAKTOR_MIN, min(FAKTOR_MAX, min(b, h)))


def faktor_setzen(neu):
    """Setzt den Faktor und zieht alle Schriften nach.  Liefert True, wenn
    sich wirklich etwas geändert hat."""
    global _faktor
    if abs(neu - _faktor) < 0.02:
        return False
    _faktor = neu
    for (_familie, groesse, _stil), sf in _schriften.items():
        sf.configure(size=max(6, round(groesse * _faktor)))
    return True


def masse(widget, **grundwerte):
    """Pixeloptionen eines Widgets merken, damit sie beim Umskalieren
    mitwachsen.  Die Werte sind Design-Pixel, so wie sie hier im Code stehen."""
    _masse.append((widget, grundwerte))
    widget.configure(**{name: px(wert) for name, wert in grundwerte.items()})
    return widget


def bei_skalierung(rueckruf):
    """Wird nach jeder Änderung des Faktors aufgerufen."""
    _horcher.append(rueckruf)
    return rueckruf


def neu_vermessen():
    """Alle gemerkten Pixelmaße und Horcher auf den neuen Faktor bringen."""
    uebrig = []
    for widget, grundwerte in _masse:
        try:
            widget.configure(**{name: px(wert) for name, wert in grundwerte.items()})
        except tk.TclError:          # Widget ist inzwischen weg
            continue
        uebrig.append((widget, grundwerte))
    _masse[:] = uebrig
    for rueckruf in list(_horcher):
        try:
            rueckruf()
        except tk.TclError:
            _horcher.remove(rueckruf)


# --- Abstände ------------------------------------------------------------
#  Die Abstände stehen ueberall als schlichte Zahlen im Code (padx=8,
#  padding=14, spacing1=6).  Sie hier einzeln zu skalieren waere hundertfach
#  derselbe Handgriff; stattdessen wird der Widget-Baum einmal durchgegangen
#  und jeder Wert beim ersten Sehen als Design-Mass gemerkt.  Danach laesst er
#  sich beliebig oft neu berechnen.
_abstaende = {}
_GITTER_MASSE = ("padx", "pady", "ipadx", "ipady")
_WIDGET_MASSE = ("padding", "padx", "pady")
_TAG_MASSE = ("spacing1", "spacing2", "spacing3", "lmargin1", "lmargin2", "rmargin")


def _als_mass(wert):
    """grid_info und cget liefern Masse mal als Zahl, mal als Text, mal als Paar."""
    if isinstance(wert, (list, tuple)):
        zahlen = tuple(_als_mass(x) for x in wert)
        return zahlen if len(zahlen) > 1 else zahlen[0]
    text = str(wert).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _mass_skaliert(wert):
    if isinstance(wert, tuple):
        return tuple(_mass_skaliert(x) for x in wert)
    return px(wert) if wert else 0


def abstaende_erfassen(widget):
    """Neue Widgets aufnehmen; bekannte bleiben bei ihrem Grundwert."""
    for kind in widget.winfo_children():
        abstaende_erfassen(kind)
        name = str(kind)
        if name in _abstaende:
            continue
        verwalter = kind.winfo_manager()
        if verwalter not in ("grid", "pack"):
            # Gerade ausgeblendet (z. B. die Formen-Einstellungen).  Tk kennt
            # die Abstaende jetzt nicht - beim naechsten Mal noch einmal
            # nachsehen, statt hier eine Null festzuschreiben.
            continue
        gitter = {}
        info = kind.grid_info() if verwalter == "grid" else kind.pack_info()
        for option in _GITTER_MASSE:
            wert = _als_mass(info.get(option))
            if wert:
                gitter[option] = wert
        optionen = {}
        for option in _WIDGET_MASSE:
            try:
                wert = _als_mass(kind.cget(option))
            except (tk.TclError, AttributeError):
                continue
            if wert:
                optionen[option] = wert
        marken = {}
        if isinstance(kind, tk.Text):
            for marke in kind.tag_names():
                werte = {}
                for option in _TAG_MASSE:
                    try:
                        wert = _als_mass(kind.tag_cget(marke, option))
                    except tk.TclError:
                        continue
                    if wert:
                        werte[option] = wert
                if werte:
                    marken[marke] = werte
        _abstaende[name] = (kind, verwalter, gitter, optionen, marken)


def abstaende_nachziehen(wurzel):
    """Neue Widgets aufnehmen und alle bekannten auf den Faktor bringen."""
    abstaende_erfassen(wurzel)
    abstaende_anwenden()


def nachziehen_bald(widget):
    """Nach dem Einblenden eines vorher versteckten Bereichs dessen Abstaende
    nachholen.  Erst im Leerlauf, weil Tk sie im selben Atemzug noch nicht
    kennt."""
    wurzel = widget.winfo_toplevel()
    wurzel.after_idle(lambda: abstaende_nachziehen(wurzel))


def abstaende_anwenden():
    for name, (kind, verwalter, gitter, optionen, marken) in list(_abstaende.items()):
        try:
            if not kind.winfo_exists():
                raise tk.TclError
            # Ein mit grid_remove ausgeblendetes Widget meldet keinen Verwalter
            # mehr - es jetzt neu zu konfigurieren wuerde es wieder einblenden.
            if gitter and kind.winfo_manager() == verwalter:
                werte = {o: _mass_skaliert(w) for o, w in gitter.items()}
                if verwalter == "grid":
                    kind.grid_configure(**werte)
                else:
                    kind.pack_configure(**werte)
            if optionen:
                kind.configure(**{o: _mass_skaliert(w) for o, w in optionen.items()})
            for marke, werte in marken.items():
                kind.tag_configure(marke, **{o: _mass_skaliert(w)
                                             for o, w in werte.items()})
        except tk.TclError:
            _abstaende.pop(name, None)


def stil_masse(stil):
    """Alle größenabhängigen Einstellungen des Themas.  Getrennt von den
    Farben, weil nur diese beim Umskalieren neu gesetzt werden müssen."""
    stil.configure("TButton", padding=(px(14), px(7)))
    for name in ("TEntry", "TCombobox", "TSpinbox"):
        stil.configure(name, padding=(px(8), px(6)))
    # Aufklapp-Pfeil und Auswahlpunkt sind sonst zwei Pixel gross und
    # verschwinden auf einem grossen Bildschirm.
    for name in ("TCombobox", "TSpinbox"):
        stil.configure(name, arrowsize=px(13))
    stil.configure("TNotebook", tabmargins=(px(2), px(6), px(2), 0))
    stil.configure("TNotebook.Tab", padding=(px(18), px(9)))
    stil.configure("Segment.TRadiobutton", padding=(px(14), px(7)))
    for name in ("TRadiobutton", "TCheckbutton"):
        stil.configure(name, padding=(px(2), px(3)),
                       indicatorsize=px(11), indicatormargin=(0, 0, px(6), 0))
    stil.configure("Treeview", rowheight=px(30))
    stil.configure("Treeview.Heading", padding=(px(8), px(8)))
    stil.configure("TProgressbar", thickness=px(6))
    for name in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        stil.configure(name, arrowsize=px(12))


def stil_einrichten(fenster):
    """Ein ruhiges, flaches Aussehen - aufgebaut auf dem Thema "clam",
    weil nur das sich durchgehend umfärben lässt."""
    stil = ttk.Style(fenster)
    if "clam" in stil.theme_names():
        stil.theme_use("clam")
    fenster.configure(background=FLAECHE)

    stil.configure(".", background=FLAECHE, foreground=TEXT,
                   fieldbackground=KARTE, bordercolor=RAND,
                   lightcolor=FLAECHE, darkcolor=FLAECHE,
                   focuscolor=BLAU, font=schrift(10))
    stil.configure("TFrame", background=FLAECHE)
    stil.configure("TLabel", background=FLAECHE, foreground=TEXT)

    # --- Knöpfe: flach, heller Rand, Akzent beim Überfahren ---
    stil.configure("TButton", background=KARTE, foreground=TEXT, relief="flat",
                   borderwidth=1, anchor="center")
    stil.map("TButton",
             background=[("pressed", BLAU_HELL), ("active", BLAU_HELL),
                         ("disabled", FLAECHE)],
             foreground=[("disabled", RAND_STARK), ("active", BLAU)],
             bordercolor=[("active", BLAU), ("focus", BLAU)])

    # --- Eingabefelder ---
    for name in ("TEntry", "TCombobox", "TSpinbox"):
        stil.configure(name, fieldbackground=KARTE, background=KARTE,
                       bordercolor=RAND, borderwidth=1, relief="flat",
                       arrowcolor=GRAU, insertcolor=TEXT)
        stil.map(name,
                 bordercolor=[("focus", BLAU), ("hover", RAND_STARK)],
                 fieldbackground=[("readonly", KARTE), ("disabled", FLAECHE)],
                 foreground=[("disabled", RAND_STARK)])
    # Die aufgeklappte Liste ist ein eigenes Tk-Listbox-Fenster und erbt den
    # ttk-Stil nicht - ohne das bleibt sie winzig.  Die benannte Schrift waechst
    # spaeter von selbst mit, die Zeile wird hier nur einmal gesetzt.
    fenster.option_add("*TCombobox*Listbox.font", schrift(11))
    fenster.option_add("*TCombobox*Listbox.background", KARTE)
    fenster.option_add("*TCombobox*Listbox.foreground", TEXT)
    fenster.option_add("*TCombobox*Listbox.selectBackground", BLAU_HELL)
    fenster.option_add("*TCombobox*Listbox.selectForeground", TEXT)

    # --- Reiter: flach, aktiver Reiter weiß mit Akzentschrift ---
    stil.configure("TNotebook", background=FLAECHE, borderwidth=0)
    stil.configure("TNotebook.Tab", background=FLAECHE, foreground=GRAU,
                   borderwidth=0, font=schrift(10))
    stil.map("TNotebook.Tab",
             background=[("selected", KARTE), ("active", BLAU_HELL)],
             foreground=[("selected", BLAU), ("active", TEXT)],
             font=[("selected", schrift(10, "bold"))])

    # --- Segmentschalter: eine Reihe Knöpfe statt winziger Auswahlkreise ---
    stil.layout("Segment.TRadiobutton", stil.layout("Toolbutton"))
    stil.configure("Segment.TRadiobutton", background=KARTE, foreground=GRAU,
                   borderwidth=1, relief="flat", anchor="center",
                   font=schrift(10))
    stil.map("Segment.TRadiobutton",
             background=[("selected", BLAU_HELL), ("active", BLAU_HELL)],
             foreground=[("selected", BLAU), ("active", TEXT)],
             bordercolor=[("selected", BLAU), ("active", RAND_STARK)],
             relief=[("selected", "flat")])

    # --- Auswahlknöpfe ---
    for name in ("TRadiobutton", "TCheckbutton"):
        stil.configure(name, background=FLAECHE, foreground=TEXT,
                       indicatorcolor=KARTE)
        stil.map(name, foreground=[("disabled", RAND_STARK), ("active", BLAU)],
                 indicatorcolor=[("selected", BLAU), ("disabled", FLAECHE)],
                 background=[("active", FLAECHE)])

    # --- Tabellen ---
    stil.configure("Treeview", background=KARTE, fieldbackground=KARTE,
                   foreground=TEXT, borderwidth=1, relief="flat")
    stil.configure("Treeview.Heading", background=FLAECHE, foreground=GRAU,
                   relief="flat", borderwidth=0,
                   font=schrift(9, "bold"))
    stil.map("Treeview.Heading", background=[("active", BLAU_HELL)],
             foreground=[("active", BLAU)])
    stil.map("Treeview", background=[("selected", BLAU_HELL)],
             foreground=[("selected", TEXT)])

    # --- Fortschritt und Bildlauf ---
    stil.configure("TProgressbar", background=BLAU, troughcolor=RAND,
                   borderwidth=0)
    stil.configure("Vertical.TScrollbar", background=RAND, troughcolor=FLAECHE,
                   borderwidth=0, arrowcolor=GRAU)
    stil.configure("Horizontal.TScrollbar", background=RAND, troughcolor=FLAECHE,
                   borderwidth=0, arrowcolor=GRAU)
    for name in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        stil.map(name, background=[("active", RAND_STARK)])

    stil_masse(stil)
    return stil

# Im Vollbild sollen Text und Eingabefelder nicht über die ganze Breite
# auseinanderlaufen - der Inhalt bleibt mittig und höchstens so breit.
MAX_INHALT = 980
MAX_TEXT = 1200
FELD_BREIT = 34            # Zeichen: einheitliche Breite der Eingabefelder
VERGROESSERUNG_MAX = 1.75  # so weit duerfen die Buchseiten-Fotos hochskaliert werden


def spalten_anpassen(tabelle, spalten, zeilen, dehnbar=(), obergrenze=420):
    """Spaltenbreiten aus dem tatsächlichen Text berechnen.

    Feste Pixelwerte gehen auf Bildschirmen mit hoher Auflösung daneben -
    dort ist dieselbe Schrift doppelt so breit und Überschriften brechen ab.
    Gemessen wird mit genau den Schriften, die die Tabelle benutzt; wächst der
    Faktor, wächst darum auch die Spalte.
    """
    kopf = schrift(9, "bold")
    inhalt = schrift(10)
    grenze = px(obergrenze)
    wunsch, kleinste = [], []
    for i, (name, titel) in enumerate(spalten):
        breite = kopf.measure(titel) + px(28)
        for z in zeilen[:300]:
            breite = max(breite, inhalt.measure(str(z[i])) + px(24))
        wunsch.append(min(breite, grenze))
        kleinste.append(min(kopf.measure(titel) + px(24), grenze))
    tabelle.spalten_wunsch = (tuple(spalten), wunsch, kleinste, tuple(dehnbar))
    spalten_einpassen(tabelle)
    if not getattr(tabelle, "spalten_gebunden", False):
        tabelle.spalten_gebunden = True
        tabelle.bind("<Configure>", lambda _e: spalten_einpassen(tabelle), add="+")


def spalten_einpassen(tabelle):
    """Die gewünschten Breiten in die Tabelle hineinquetschen.

    Ohne das faellt die letzte Spalte in einem schmalen Fenster rechts heraus,
    und es gibt keinen Balken, mit dem man sie zurueckholen koennte.  Zuerst
    geben die dehnbaren Spalten nach, danach notfalls die uebrigen - nie unter
    die Breite ihrer eigenen Ueberschrift."""
    daten = getattr(tabelle, "spalten_wunsch", None)
    if not daten:
        return
    spalten, wunsch, kleinste, dehnbar = daten
    breiten = list(wunsch)
    # Ein paar Pixel fuer den eigenen Rahmen abziehen, sonst bleibt die
    # Tabelle genau diese Pixel zu breit.
    platz = tabelle.winfo_width() - px(4)
    if platz > 1:
        gruppen = ([i for i, (n, _t) in enumerate(spalten) if n in dehnbar],
                   list(range(len(spalten))))
        for auswahl in gruppen:
            zuviel = sum(breiten) - platz
            if zuviel <= 0:
                break
            spielraum = sum(max(0, breiten[i] - kleinste[i]) for i in auswahl)
            if spielraum <= 0:
                continue
            anteil = min(1.0, zuviel / spielraum)
            for i in auswahl:
                breiten[i] -= int((breiten[i] - kleinste[i]) * anteil)
            # Der Rest aus dem Abrunden: von der breitesten Spalte abziehen.
            rest = sum(breiten) - platz
            if rest > 0:
                breiteste = max(auswahl, key=lambda i: breiten[i] - kleinste[i])
                breiten[breiteste] -= min(rest, breiten[breiteste] - kleinste[breiteste])
    if getattr(tabelle, "spalten_gesetzt_auf", None) == breiten:
        return                      # sonst loest das Setzen sich selbst aus
    tabelle.spalten_gesetzt_auf = list(breiten)
    for i, (name, _titel) in enumerate(spalten):
        tabelle.column(name, width=breiten[i], minwidth=kleinste[i],
                       stretch=(name in dehnbar))


def segmente(eltern, variable, eintraege, befehl=None):
    """Eine Reihe zusammenhängender Schalter - lesbarer als kleine Kreise."""
    rahmen = ttk.Frame(eltern)
    for i, (wert, beschriftung) in enumerate(eintraege):
        ttk.Radiobutton(rahmen, text=beschriftung, value=wert, variable=variable,
                        style="Segment.TRadiobutton", command=befehl,
                        takefocus=True).grid(row=0, column=i,
                                             padx=(0 if i == 0 else px(2), 0))
    return rahmen


def umbruch_koppeln(behaelter, labels, rand=40, maximum=1400):
    """Laesst die Umbruchbreite der Labels mit dem Fenster wachsen."""
    zuletzt = [0]

    def anpassen(_ereignis=None):
        breite = max(px(280), min(px(maximum), behaelter.winfo_width() - px(rand)))
        if breite != zuletzt[0]:
            zuletzt[0] = breite
            for label in labels:
                try:
                    label.configure(wraplength=breite)
                except tk.TclError:
                    pass

    behaelter.bind("<Configure>", anpassen)
    bei_skalierung(anpassen)


def zentriert(eltern, maxbreite=MAX_INHALT):
    """Liefert (aussen, innen).  'aussen' wird wie gewohnt eingehängt, der
    Inhalt kommt in 'innen' und bleibt mittig und höchstens maxbreite breit.

    Die Grenze ist ein Design-Maß: sie wächst mit, sonst bliebe im Vollbild
    eine schmale Spalte in der Mitte stehen und links und rechts wäre nichts."""
    aussen = ttk.Frame(eltern)
    aussen.rowconfigure(0, weight=1)
    aussen.columnconfigure(0, weight=1)
    aussen.columnconfigure(1, weight=0)
    aussen.columnconfigure(2, weight=1)
    innen = ttk.Frame(aussen)
    innen.grid(row=0, column=1, sticky="nsew")

    zuletzt = [0]

    def anpassen(_ereignis=None):
        breite = min(px(maxbreite), max(px(300), aussen.winfo_width()))
        if breite != zuletzt[0]:        # sonst löst das Umbauen sich selbst aus
            zuletzt[0] = breite
            aussen.columnconfigure(1, minsize=breite)

    aussen.bind("<Configure>", anpassen)
    bei_skalierung(anpassen)
    return aussen, innen


# --------------------------------------------------------------------------
#  Suche
# --------------------------------------------------------------------------

class SuchReiter(ttk.Frame):
    """Eingabefeld oben, Ergebnis darunter.  Gesucht wird beim Tippen."""

    def __init__(self, master, app):
        super().__init__(master, padding=14)
        self.app = app
        self.db = app.db
        self._timer = None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        aussen, inhalt = zentriert(self, MAX_TEXT)
        aussen.grid(row=0, column=0, sticky="nsew")
        self.inhalt = inhalt
        inhalt.columnconfigure(0, weight=1)
        inhalt.rowconfigure(2, weight=1)

        kopf = ttk.Frame(inhalt)
        kopf.grid(row=0, column=0, sticky="ew")
        kopf.columnconfigure(1, weight=1)

        ttk.Label(kopf, text="Wort:", font=schrift(10)).grid(row=0, column=0, padx=(0, 8))
        self.eingabe = ttk.Entry(kopf, font=schrift(13))
        self.eingabe.grid(row=0, column=1, sticky="ew", ipady=4)
        self.eingabe.bind("<KeyRelease>", self._getippt)
        self.eingabe.bind("<Return>", lambda _e: self._suchen())
        self.eingabe.bind("<Escape>", lambda _e: self._leeren())

        self.formen_knopf = ttk.Button(kopf, text="Alle Formen", command=self._formen,
                                       state="disabled")
        self.formen_knopf.grid(row=0, column=2, padx=(8, 0))

        hinweis = ttk.Label(inhalt, foreground=GRAU, font=schrift(9), justify="left",
                            text="Lateinisch (auch gebeugt: rogaverunt, altissimum) oder "
                                 "deutsch. Mehrere Wörter gehen auch: castra posuerunt")
        hinweis.grid(row=1, column=0, sticky="w", pady=(6, 10))
        umbruch_koppeln(inhalt, [hinweis], maximum=MAX_TEXT)

        rahmen = ttk.Frame(inhalt)
        rahmen.grid(row=2, column=0, sticky="nsew")
        rahmen.columnconfigure(0, weight=1)
        rahmen.rowconfigure(0, weight=1)

        self.ausgabe = tk.Text(rahmen, wrap="word", font=schrift(11, familie=MONO), padx=12, pady=10,
                               width=20, height=8, relief="flat", borderwidth=1, highlightthickness=1,
                               highlightbackground=RAND, highlightcolor=RAND,
                               state="disabled", background=KARTE, foreground=TEXT)
        self.ausgabe.grid(row=0, column=0, sticky="nsew")
        leiste = ttk.Scrollbar(rahmen, orient="vertical", command=self.ausgabe.yview)
        leiste.grid(row=0, column=1, sticky="ns")
        self.ausgabe.configure(yscrollcommand=leiste.set)

        self.ausgabe.tag_configure("titel", font=schrift(13, "bold"), foreground=BLAU,
                                   spacing1=8, spacing3=4)
        self.ausgabe.tag_configure("abschnitt", font=schrift(10, "bold"), foreground=GRAU,
                                   spacing1=10, spacing3=2)
        self.ausgabe.tag_configure("bestimmung", font=schrift(11, "bold"), foreground=GRUEN)
        self.ausgabe.tag_configure("normal", font=schrift(11))
        self.ausgabe.tag_configure("leise", font=schrift(10), foreground=GRAU)

        self._zeigen([("Gib oben ein Wort ein.", "leise")])

    # -------------------------------------------------- Eingabe
    def _getippt(self, ereignis):
        if ereignis.keysym in ("Up", "Down", "Left", "Right", "Shift_L", "Shift_R"):
            return
        if self._timer:
            self.after_cancel(self._timer)
        self._timer = self.after(180, self._suchen)      # erst kurz warten

    def _leeren(self):
        self.eingabe.delete(0, "end")
        self._zeigen([("Gib oben ein Wort ein.", "leise")])

    def suche_mit(self, wort):
        """Von aussen aufrufbar (z. B. aus dem Quiz heraus)."""
        self.eingabe.delete(0, "end")
        self.eingabe.insert(0, wort)
        self._suchen()
        self.eingabe.focus_set()

    # -------------------------------------------------- Ausgabe
    def _zeigen(self, stuecke):
        self.ausgabe.configure(state="normal")
        self.ausgabe.delete("1.0", "end")
        for text, tag in stuecke:
            self.ausgabe.insert("end", text + "\n", tag)
        self.ausgabe.configure(state="disabled")
        self.ausgabe.yview_moveto(0)

    def _gruppe_stuecke(self, gid, info=None, deutsch_treffer=False, einzug=""):
        g = self.db.groups[gid]
        kopf = f"{einzug}{g['lemma']}   ({g['wortart']}"
        if g["wortart"] == "Verb" and g.get("conj"):
            kopf += f", {CONJ_NAMES[g['conj']]}"
        stuecke = [(kopf + ")", "titel")]
        if info:
            if info.get("enclitic"):
                stuecke.append((f"{einzug}   Angehängtes {info['enclitic']} erkannt", "leise"))
            if info["labels"]:
                # Die Klammerhinweise stehen einmal darunter statt in jeder
                # einzelnen Bestimmung.
                sauber, notizen = [], []
                for label in info["labels"][:6]:
                    sauber.append(quiz.sauberes_label(label))
                    for notiz in re.findall(r"\[([^\]]*)\]", label):
                        if notiz not in notizen:
                            notizen.append(notiz)
                if len(info["labels"]) > 6:
                    sauber.append("…")
                stuecke.append((f"{einzug}   " + "   /   ".join(sauber), "bestimmung"))
                for notiz in notizen:
                    stuecke.append((f"{einzug}   ({notiz})", "leise"))
            elif info["lemma"]:
                stuecke.append((f"{einzug}   Grundform", "bestimmung"))
        if deutsch_treffer:
            stuecke.append((f"{einzug}   (über die deutsche Bedeutung gefunden)", "leise"))
        for e in sorted(g["entries"], key=lambda x: x["lektion"]):
            stuecke.append((f"{einzug}   [Lektion {e['lektion']}]  {e['deutsch']}", "normal"))
            teile = [f"{FORMEN_LABEL.get(k, k)}: {v}" for k, v in e.get("formen", {}).items()]
            if teile:
                stuecke.append((f"{einzug}      " + "   |   ".join(teile), "leise"))
            zusatz = []
            for schluessel, beschriftung in (("genus", "Genus"), ("deklination", "Deklination"),
                                             ("numerus", "nur"), ("kasus", "Kasus")):
                if e.get(schluessel):
                    zusatz.append(f"{beschriftung} {e[schluessel]}")
            if zusatz:
                stuecke.append((f"{einzug}      " + "   |   ".join(zusatz), "leise"))
        return stuecke

    def _suchen(self):
        self._timer = None
        wort = self.eingabe.get().strip()
        self.aktuelle_gruppen = []
        if not wort:
            self.formen_knopf.configure(state="disabled")
            self._zeigen([("Gib oben ein Wort ein.", "leise")])
            return

        res = self.db.search(wort)
        stuecke = []
        lat = res["latein"]
        if lat:
            reihe = sorted(lat.items(), key=lambda kv: not kv[1]["lemma"])
            stuecke.append(("LATEINISCH", "abschnitt"))
            for gid, info in reihe:
                stuecke += self._gruppe_stuecke(gid, info)
                self.aktuelle_gruppen.append(gid)
        if res["deutsch"]:
            gezeigt = 0
            for gid, _typ in res["deutsch"]:
                if gid in lat:
                    continue
                if gezeigt == 0:
                    stuecke.append(("DEUTSCHE BEDEUTUNG", "abschnitt"))
                stuecke += self._gruppe_stuecke(gid, None, deutsch_treffer=True)
                self.aktuelle_gruppen.append(gid)
                gezeigt += 1
                if gezeigt >= 12:
                    stuecke.append(("   … weitere Treffer nicht angezeigt", "leise"))
                    break
        if res["woerter"]:
            stuecke.append(("WORT FÜR WORT", "abschnitt"))
            for tok, treffer in res["woerter"]:
                stuecke.append((f"   ▸ {tok}", "normal"))
                for gid, info in treffer.items():
                    stuecke += self._gruppe_stuecke(gid, info, einzug="   ")
                    self.aktuelle_gruppen.append(gid)
        if res["wendungen"]:
            stuecke.append(("KOMMT AUSSERDEM VOR IN", "abschnitt"))
            for gid in res["wendungen"][:8]:
                g = self.db.groups[gid]
                e = g["entries"][0]
                stuecke.append((f"   {g['lemma']}  –  {e['deutsch']}  [Lektion {e['lektion']}]",
                                "normal"))
        if not stuecke:
            stuecke.append((f"Keine Vokabel zu „{wort}“ gefunden.", "titel"))
            if res["vorschlaege"]:
                stuecke.append(("MEINTEST DU VIELLEICHT", "abschnitt"))
                for gid, wert, text in res["vorschlaege"]:
                    stuecke.append((f"   {text}    [{int(wert * 100)} %]", "normal"))
                    self.aktuelle_gruppen.append(gid)
            else:
                stuecke.append(("Auch keine ähnlichen Wörter gefunden.", "leise"))

        self.formen_knopf.configure(
            state="normal" if any(self.db.groups[g].get("par") for g in self.aktuelle_gruppen)
            else "disabled")
        self._zeigen(stuecke)

    # -------------------------------------------------- Formentabelle
    def _formen(self):
        for gid in self.aktuelle_gruppen:
            if self.db.groups[gid].get("par"):
                FormenFenster(self, self.db, gid)
                return


class FormenFenster(tk.Toplevel):
    """Eigenes Fenster mit der vollstaendigen Formentabelle."""

    def __init__(self, master, db, gid):
        super().__init__(master)
        g = db.groups[gid]
        self.title(f"Formen von {g['lemma']}")
        self.geometry(f"{px(680)}x{px(620)}")
        self.transient(master.winfo_toplevel())
        self.configure(background=FLAECHE)
        self.after_idle(lambda: abstaende_nachziehen(self))

        rahmen = ttk.Frame(self, padding=12)
        rahmen.pack(fill="both", expand=True)
        rahmen.columnconfigure(0, weight=1)
        rahmen.rowconfigure(1, weight=1)

        ttk.Label(rahmen, text=f"{g['lemma']}   ({g['wortart']})",
                  font=schrift(15, "bold"), foreground=BLAU).grid(row=0, column=0, sticky="w",
                                                                    pady=(0, 8))

        innen = ttk.Frame(rahmen)
        innen.grid(row=1, column=0, sticky="nsew")
        innen.columnconfigure(0, weight=1)
        innen.rowconfigure(0, weight=1)

        text = tk.Text(innen, wrap="word", font=schrift(10, familie=MONO), padx=10, pady=8,
                       width=24, height=12, relief="flat", borderwidth=0,
                       highlightthickness=1, highlightbackground=RAND,
                       background=KARTE, foreground=TEXT)
        text.grid(row=0, column=0, sticky="nsew")
        leiste = ttk.Scrollbar(innen, orient="vertical", command=text.yview)
        leiste.grid(row=0, column=1, sticky="ns")
        text.configure(yscrollcommand=leiste.set)
        text.tag_configure("label", font=schrift(10, "bold"), foreground=GRAU)
        text.tag_configure("form", font=schrift(11, familie=MONO))

        gruppiert = {}
        for label, person, alts in g["par"].rows:
            voll = label + (", " + person if person else "")
            gruppiert.setdefault(label, []).append((voll, " / ".join(alts)))
        for label, zeilen in gruppiert.items():
            # Einzeiler (Substantive, Infinitive) brauchen keine eigene
            # Ueberschrift - Bezeichnung und Form passen in eine Zeile.
            if len(zeilen) == 1 and not zeilen[0][0][len(label):].strip(", "):
                text.insert("end", f"{label:<34}", "label")
                text.insert("end", f"{zeilen[0][1]}\n", "form")
                continue
            text.insert("end", label + "\n", "label")
            for voll, formen in zeilen:
                rest = voll[len(label):].strip(", ")
                text.insert("end", f"    {rest:<22} {formen}\n", "form")
            text.insert("end", "\n")
        text.configure(state="disabled")

        ttk.Button(rahmen, text="Schließen", command=self.destroy).grid(row=2, column=0,
                                                                        sticky="e", pady=(10, 0))
        self.bind("<Escape>", lambda _e: self.destroy())


# --------------------------------------------------------------------------
#  Quiz
# --------------------------------------------------------------------------

class QuizReiter(ttk.Frame):
    """Drei Ansichten im selben Reiter: Einstellungen, Frage, Ergebnis."""

    def __init__(self, master, app):
        super().__init__(master, padding=14)
        self.app = app
        self.db = app.db
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.phase = None
        self.ansicht_einstellungen = self._baue_einstellungen()
        self.ansicht_frage = self._baue_frage()
        self.ansicht_ergebnis = self._baue_ergebnis()
        self._zeige(self.ansicht_einstellungen)

        # Weiterblaettern mit Enter ODER Leertaste, egal worauf der Fokus liegt.
        # Am Fenster gebunden, weil der Fokus nach dem Pruefen auf dem Knopf
        # sitzt und ein Entry-Binding dort nicht mehr greift.
        oben = self.winfo_toplevel()
        oben.bind("<Return>", self._weiter_taste, add="+")
        oben.bind("<KP_Enter>", self._weiter_taste, add="+")
        oben.bind("<space>", self._weiter_taste, add="+")

    def _weiter_taste(self, ereignis):
        """Nur wenn die Auflösung sichtbar ist - und nie beim Tippen."""
        if self.phase != "antwort":
            return None
        if isinstance(ereignis.widget, (ttk.Entry, tk.Entry, tk.Text, ttk.Combobox)):
            return None          # Leerzeichen im Suchfeld nicht abfangen
        self._naechste()
        return "break"

    def _zeige(self, ansicht):
        for a in (self.ansicht_einstellungen, self.ansicht_frage, self.ansicht_ergebnis):
            a.grid_forget()
        ansicht.grid(row=0, column=0, sticky="nsew")
        nachziehen_bald(self)

    # -------------------------------------------------- Einstellungen
    def _baue_einstellungen(self):
        aussen, f = zentriert(self)
        f.columnconfigure(1, weight=1)
        zeile = 0

        ttk.Label(f, text="Quiz einstellen", font=schrift(16, "bold")).grid(
            row=zeile, column=0, columnspan=2, sticky="w", pady=(0, 2))
        zeile += 1
        self.lernstand = masse(ttk.Label(f, text="", foreground=GRAU, font=schrift(10),
                                         justify="left"),
                               wraplength=MAX_INHALT - 20)
        self.lernstand.grid(row=zeile, column=0, columnspan=2, sticky="w", pady=(0, 14))
        zeile += 1

        vorhanden = sorted({e["lektion"] for e in self.db.entries})
        self.lektionen_vorhanden = vorhanden

        # Die Zelle daneben ist zwei Zeilen hoch (Feld + Beispiel).  Ohne "n"
        # rutscht die Beschriftung in deren Mitte und steht schief zum Feld;
        # die 7 sind der Innenabstand des Eingabefeldes.
        ttk.Label(f, text="Lektionen:", font=schrift(10)).grid(
            row=zeile, column=0, sticky="nw", pady=(13, 0))
        kasten = ttk.Frame(f)
        kasten.grid(row=zeile, column=1, sticky="w", pady=(6, 0))
        self.lektionen_feld = ttk.Entry(kasten, font=schrift(11), width=FELD_BREIT)
        self.lektionen_feld.insert(0, "alle")
        self.lektionen_feld.grid(row=0, column=0, sticky="w")
        ttk.Label(kasten, foreground=GRAU, font=schrift(9), justify="left",
                  text=f"z. B. 1-8  ·  3,5  ·  alle   (vorhanden: {vorhanden[0]}–{vorhanden[-1]})"
                  ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        zeile += 1

        ttk.Label(f, text="Wortart:", font=schrift(10)).grid(
            row=zeile, column=0, sticky="w", pady=8)
        arten = ["alle"] + [w for w in WORTART_ORDER
                            if any(g["wortart"] == w for g in self.db.groups)]
        self.wortart_wahl = ttk.Combobox(f, values=arten, state="readonly",
                                         font=schrift(11), width=FELD_BREIT - 2)
        self.wortart_wahl.current(0)
        self.wortart_wahl.grid(row=zeile, column=1, sticky="w", pady=8)
        zeile += 1

        ttk.Label(f, text="Modus:", font=schrift(10)).grid(
            row=zeile, column=0, sticky="w", pady=(10, 6))
        self.modus = tk.StringVar(value="ld")
        segmente(f, self.modus,
                 (("ld", "Latein → Deutsch"), ("dl", "Deutsch → Latein"),
                  ("mix", "gemischt"), ("formen", "Formen-Quiz")),
                 self._modus_gewechselt).grid(row=zeile, column=1, sticky="w", pady=(10, 6))
        zeile += 1

        # --- nur für das Formen-Quiz ---
        self.formen_block = ttk.Frame(f)
        self.formen_block.grid(row=zeile, column=0, columnspan=2, sticky="ew", pady=(4, 6))
        self.formen_block.columnconfigure(1, weight=1)

        ttk.Label(self.formen_block, text="Formen bis:",
                  font=schrift(10)).grid(row=0, column=0, sticky="w", pady=5)
        self.bis_lektion = ttk.Combobox(
            self.formen_block, state="readonly", width=FELD_BREIT - 2, font=schrift(10),
            values=["passend zur Lektionsauswahl", "alle Formen (auch Konjunktiv usw.)"]
                   + [f"bis Lektion {n}" for n in self.lektionen_vorhanden])
        self.bis_lektion.current(0)
        self.bis_lektion.grid(row=0, column=1, sticky="w", pady=5)

        ttk.Label(self.formen_block, text="Grammatik:",
                  font=schrift(10)).grid(row=1, column=0, sticky="w", pady=5)
        self.formen_bereich = ttk.Combobox(
            self.formen_block, state="readonly", width=FELD_BREIT - 2, font=schrift(10),
            values=[n for n, _p in quiz.FORM_BEREICHE])
        self.formen_bereich.current(0)
        self.formen_bereich.grid(row=1, column=1, sticky="w", pady=5)

        ttk.Label(self.formen_block, text="Abfrage:",
                  font=schrift(10)).grid(row=2, column=0, sticky="w", pady=5)
        self.formen_art = tk.StringVar(value="gemischt")
        segmente(self.formen_block, self.formen_art, quiz.ARTEN).grid(
            row=2, column=1, sticky="w", pady=5)
        zeile += 1

        ttk.Label(f, text="Fragen:", font=schrift(10)).grid(
            row=zeile, column=0, sticky="w", pady=8)
        anzahl_zeile = ttk.Frame(f)
        anzahl_zeile.grid(row=zeile, column=1, sticky="w", pady=8)
        self.anzahl = tk.StringVar(value="10")
        ttk.Combobox(anzahl_zeile, textvariable=self.anzahl, width=8, font=schrift(11),
                     values=("alle", "5", "10", "20", "30", "50", "100")
                     ).pack(side="left")
        ttk.Label(anzahl_zeile, text="„alle“ fragt jede Vokabel der Auswahl genau einmal ab",
                  foreground=GRAU, font=schrift(9)).pack(side="left", padx=(12, 0))
        zeile += 1

        self.einstellungen_hinweis = ttk.Label(f, text="", foreground=ROT, font=schrift(10))
        self.einstellungen_hinweis.grid(row=zeile, column=0, columnspan=2, sticky="w", pady=(10, 0))
        zeile += 1

        ttk.Button(f, text="Quiz starten", command=self._starten).grid(
            row=zeile, column=0, columnspan=2, sticky="w", pady=(16, 0), ipadx=18, ipady=6)

        self._modus_gewechselt()
        return aussen

    def _modus_gewechselt(self):
        """Die Formen-Einstellungen nur im Formen-Quiz anzeigen."""
        if self.modus.get() == "formen":
            self.formen_block.grid()
            nachziehen_bald(self)
        else:
            self.formen_block.grid_remove()

    # -------------------------------------------------- Frage
    def _baue_frage(self):
        aussen, f = zentriert(self)
        f.columnconfigure(0, weight=1)
        f.rowconfigure(2, weight=1)

        kopf = ttk.Frame(f)
        kopf.grid(row=0, column=0, sticky="ew")
        kopf.columnconfigure(0, weight=1)
        self.fortschritt_text = ttk.Label(kopf, text="", foreground=GRAU, font=schrift(10))
        self.fortschritt_text.grid(row=0, column=0, sticky="w")
        ttk.Button(kopf, text="Quiz beenden", command=self._abbrechen).grid(row=0, column=1,
                                                                            sticky="e")
        self.balken = ttk.Progressbar(f, mode="determinate")
        self.balken.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        f.rowconfigure(2, weight=1)

        mitte = ttk.Frame(f)
        mitte.grid(row=2, column=0, sticky="nsew", pady=16)
        mitte.columnconfigure(0, weight=1)
        mitte.rowconfigure(6, weight=1)       # der Rest bleibt unten frei

        self.frage_untertitel = ttk.Label(mitte, text="", foreground=GRAU, font=schrift(10))
        self.frage_untertitel.grid(row=0, column=0, sticky="w")
        self.frage_text = ttk.Label(mitte, text="", font=schrift(26, "bold"),
                                    foreground=BLAU, wraplength=px(680), justify="left")
        self.frage_text.grid(row=1, column=0, sticky="w", pady=(4, 2))
        self.frage_zusatz = ttk.Label(mitte, text="", foreground=GRAU, font=schrift(11),
                                      wraplength=px(680), justify="left")
        self.frage_zusatz.grid(row=2, column=0, sticky="w")
        self.umbruch_labels = [self.frage_text, self.frage_zusatz]
        self.mitte = mitte
        mitte.bind("<Configure>", self._umbruch_anpassen)
        bei_skalierung(self._umbruch_anpassen)

        self.antwort_feld = ttk.Entry(mitte, font=schrift(15))
        self.antwort_feld.grid(row=3, column=0, sticky="ew", pady=(20, 6), ipady=6)
        # "break": sonst wandert dasselbe Enter noch ans Fenster weiter und
        # ueberspringt die gerade erst gezeigte Auflösung.
        self.antwort_feld.bind("<Return>", lambda _e: (self._eingabetaste(), "break")[1])

        self.pruef_knopf = ttk.Button(mitte, text="Prüfen", command=self._eingabetaste)
        self.pruef_knopf.grid(row=4, column=0, sticky="w", ipadx=14, ipady=4)

        rueck = ttk.Frame(mitte)
        rueck.grid(row=5, column=0, sticky="new", pady=(18, 0))
        rueck.columnconfigure(0, weight=1)
        # Platz reservieren, damit die Frage beim Pruefen nicht springt
        self.rueck = rueck
        self._platz_reservieren()
        bei_skalierung(self._platz_reservieren)
        self.urteil = ttk.Label(rueck, text="", font=schrift(15, "bold"))
        self.urteil.grid(row=0, column=0, sticky="w")
        self.loesung_text = ttk.Label(rueck, text="", font=schrift(13), wraplength=px(680),
                                      justify="left")
        self.loesung_text.grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.formen_text = ttk.Label(rueck, text="", foreground=TEXT,
                                     font=schrift(11), wraplength=px(680), justify="left")
        self.formen_text.grid(row=2, column=0, sticky="w", pady=(2, 0))
        self.hinweis_text = ttk.Label(rueck, text="", foreground=GRAU, font=schrift(10),
                                      wraplength=px(680), justify="left")
        self.hinweis_text.grid(row=3, column=0, sticky="w", pady=(2, 0))
        self.merker_text = ttk.Label(rueck, text="", foreground=BLAU, font=schrift(10),
                                     wraplength=px(680), justify="left")
        self.merker_text.grid(row=4, column=0, sticky="w", pady=(6, 0))
        self.umbruch_labels += [self.loesung_text, self.formen_text,
                                self.hinweis_text, self.merker_text]
        return aussen

    def _platz_reservieren(self):
        """Platz fuer Urteil und Loesung freihalten - sonst springt die Frage
        beim Pruefen nach oben.  Waechst mit der Schrift mit."""
        for zeile, hoehe in enumerate((34, 30, 26, 22, 24)):
            self.rueck.rowconfigure(zeile, minsize=px(hoehe))

    def _umbruch_anpassen(self, ereignis=None):
        """Text soll die ganze Fensterbreite nutzen, nicht feste 680 Pixel."""
        breite = ereignis.width if ereignis is not None else self.mitte.winfo_width()
        breite = max(px(300), breite - px(20))
        for label in self.umbruch_labels:
            try:
                label.configure(wraplength=breite)
            except tk.TclError:
                pass

    # -------------------------------------------------- Ergebnis
    def _baue_ergebnis(self):
        aussen, f = zentriert(self)
        f.columnconfigure(0, weight=1)
        f.rowconfigure(2, weight=1)
        self.ergebnis_text = ttk.Label(f, text="", font=schrift(22, "bold"))
        self.ergebnis_text.grid(row=0, column=0, sticky="w")
        self.ergebnis_unter = ttk.Label(f, text="", foreground=GRAU, font=schrift(11),
                                        justify="left")
        self.ergebnis_unter.grid(row=1, column=0, sticky="w", pady=(4, 12))

        rahmen = ttk.Frame(f)
        rahmen.grid(row=2, column=0, sticky="nsew")
        rahmen.columnconfigure(0, weight=1)
        rahmen.rowconfigure(0, weight=1)
        self.fehler_liste = tk.Listbox(rahmen, font=schrift(11, familie=MONO), relief="flat",
                                       borderwidth=0, highlightthickness=1,
                                       highlightbackground=RAND, background=KARTE,
                                       foreground=TEXT, activestyle="none",
                                       selectbackground=BLAU_HELL,
                                       selectforeground=TEXT)
        self.fehler_liste.grid(row=0, column=0, sticky="nsew")
        leiste = ttk.Scrollbar(rahmen, orient="vertical", command=self.fehler_liste.yview)
        leiste.grid(row=0, column=1, sticky="ns")
        self.fehler_liste.configure(yscrollcommand=leiste.set)
        self.fehler_liste.bind("<Double-Button-1>", self._fehler_nachschlagen)

        masse(ttk.Label(f, text="Doppelklick auf ein Wort schlägt es in der Suche nach.",
                        foreground=GRAU, font=schrift(9), justify="left"),
              wraplength=700).grid(row=3, column=0, sticky="w", pady=(6, 0))
        knoepfe = ttk.Frame(f)
        knoepfe.grid(row=4, column=0, sticky="w", pady=(14, 0))
        ttk.Button(knoepfe, text="Nochmal", command=self._wiederholen).pack(
            side="left", ipadx=14, ipady=4)
        ttk.Button(knoepfe, text="Einstellungen", command=self._zurueck).pack(
            side="left", padx=(10, 0), ipadx=14, ipady=4)
        return aussen

    def _fehler_nachschlagen(self, _ereignis=None):
        wahl = self.fehler_liste.curselection()
        if not wahl:
            return
        eintrag = self.fehler_eintraege[wahl[0]]
        self.app.zur_suche(eintrag["latein"])

    # -------------------------------------------------- Ablauf
    def _starten(self):
        lektionen = quiz.lektionen_parsen(self.lektionen_feld.get(), self.lektionen_vorhanden)
        if not lektionen:
            erste, letzte = self.lektionen_vorhanden[0], self.lektionen_vorhanden[-1]
            self.einstellungen_hinweis.configure(
                text=f"Keine gültige Lektionsangabe.  Es gibt die Lektionen {erste}–{letzte}.  "
                     f"Beispiele:  1-8   ·   3,5   ·   alle")
            return
        wortart = self.wortart_wahl.get()
        wortarten = None if wortart == "alle" else {wortart}
        modus = self.modus.get()
        bis_lektion, bereich, art = self._formen_einstellung(lektionen)

        paare = quiz.gruppen_waehlen(self.db, lektionen, wortarten)
        if modus == "formen":
            paare = [(g, e) for g, e in paare
                     if quiz.formen_zeilen(g, bis_lektion, bereich)]
        if not paare:
            self.einstellungen_hinweis.configure(
                text="Zu dieser Auswahl gibt es keine Vokabeln.  Bitte anders wählen.")
            return
        wunsch = self.anzahl.get().strip().lower()
        if wunsch in ("alle", "all", "*", ""):
            anzahl = len(paare)
        else:
            try:
                anzahl = max(1, min(2000, int(wunsch)))
            except ValueError:
                anzahl = min(10, len(paare))
        self.einstellungen_hinweis.configure(text="")
        self._beginnen(paare, modus, (bis_lektion, bereich, art), anzahl)

    def _formen_einstellung(self, lektionen):
        """(bis_lektion, bereich, art) aus den drei Auswahlfeldern."""
        wahl = self.bis_lektion.get()
        if wahl.startswith("alle"):
            bis = None
        elif wahl.startswith("bis Lektion"):
            bis = int(wahl.rsplit(" ", 1)[1])
        else:
            bis = max(lektionen) if lektionen else None
        bereich = dict(quiz.FORM_BEREICHE).get(self.formen_bereich.get())
        return bis, bereich, self.formen_art.get()

    def starte_mit(self, paare, modus="ld", formen=None, anzahl=None):
        """Quiz über eine fertige Wortliste - benutzt der Fehler-Reiter."""
        if not paare:
            return False
        self._beginnen(paare, modus, formen or (None, None, "gemischt"),
                       anzahl or len(paare))
        return True

    def _beginnen(self, paare, modus, formen, anzahl):
        self.aufgaben = (random.sample(paare, anzahl) if anzahl <= len(paare)
                         else random.choices(paare, k=anzahl))
        self.einstellung = (modus, formen)
        self.nummer, self.punkte = 0, 0
        self.zaehler = {quiz.PERFEKT: 0, quiz.RICHTIG: 0, quiz.FALSCH: 0}
        self.fehler_eintraege = []
        self.balken.configure(maximum=len(self.aufgaben), value=0)
        self._zeige(self.ansicht_frage)
        self._naechste()

    def _wiederholen(self):
        self._starten()

    def _zurueck(self):
        self.lernstand_auffrischen()
        self._zeige(self.ansicht_einstellungen)

    def lernstand_auffrischen(self):
        s = self.app.statistik.zahlen()
        self.lernstand.configure(
            text=f"Bisher gelernt: {s['einzelne']} einzelne Vokabeln  ·  "
                 f"{s['abfragen']} Abfragen   "
                 f"(★ {s['perfekt']} perfekt  ·  ✓ {s['richtig']} richtig  ·  "
                 f"✗ {s['falsch']} falsch)")

    def _abbrechen(self):
        if self.nummer:
            self._ergebnis()
        else:
            self._zeige(self.ansicht_einstellungen)

    def _naechste(self):
        if self.nummer >= len(self.aufgaben):
            self._ergebnis()
            return
        gruppe, eintrag = self.aufgaben[self.nummer]
        modus, formen = self.einstellung
        self.frage = self._baue_aufgabe(gruppe, eintrag, modus, formen)
        if self.frage is None:                   # keine Formen -> Aufgabe ueberspringen
            self.aufgaben.pop(self.nummer)
            self.balken.configure(maximum=max(1, len(self.aufgaben)))
            self._naechste()
            return

        z = self.zaehler
        self.fortschritt_text.configure(
            text=f"Frage {self.nummer + 1} von {len(self.aufgaben)}   ·   "
                 f"★ {z[quiz.PERFEKT]} perfekt   ✓ {z[quiz.RICHTIG]} richtig   "
                 f"✗ {z[quiz.FALSCH]} falsch")
        self.balken.configure(value=self.nummer)
        self.frage_untertitel.configure(text=self.frage["untertitel"])
        self.frage_text.configure(text=self.frage["frage"])
        self.frage_zusatz.configure(text=self.frage.get("zusatz", ""))
        self.antwort_feld.configure(state="normal")
        self.antwort_feld.delete(0, "end")
        self.antwort_feld.focus_set()
        self.urteil.configure(text="")
        self.loesung_text.configure(text="")
        self.formen_text.configure(text="")
        self.hinweis_text.configure(text="")
        self.merker_text.configure(text="")
        self.pruef_knopf.configure(text="Prüfen")
        self.phase = "frage"

    def _baue_aufgabe(self, gruppe, eintrag, modus, formen):
        """Eine Aufgabe als dict:  frage, untertitel, loesung, pruefer."""
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

                return {
                    "frage": gruppe["lemma"],
                    "untertitel": f"Bilde die Form:  {bestimmung}",
                    "zusatz": eintrag["deutsch"],
                    "loesung": " / ".join(alts),
                    "pruefer": pruefe_form,
                }
            return {
                "frage": alts[0],
                "untertitel": "Von welcher Vokabel stammt diese Form?",
                "zusatz": "",
                "loesung": f"{gruppe['lemma']}   ({bestimmung})   –   {eintrag['deutsch']}",
                "pruefer": lambda a: (quiz.pruefe_latein(a, gruppe, self.db)[0], None),
            }

        richtung = 1 if modus == "ld" else 2 if modus == "dl" else random.choice((1, 2))
        kopf = f"Lektion {eintrag['lektion']}  ·  {gruppe['wortart']}"
        if richtung == 1:
            return {
                "frage": eintrag["latein"],
                "untertitel": f"{kopf}   ·   ins Deutsche",
                "loesung": eintrag["deutsch"],
                "pruefer": lambda a: (
                    quiz.pruefe_deutsch(a, eintrag, self.db, gruppe)[0], None),
            }

        def pruefe(antwort):
            bewertung, _treffer, form = quiz.pruefe_latein(antwort, gruppe, self.db)
            hinweis = (f"Das ist {form} – die Grundform heißt {eintrag['latein']}."
                       if form else None)
            return bewertung, hinweis

        return {
            "frage": eintrag["deutsch"],
            "untertitel": f"{kopf}   ·   ins Lateinische",
            "loesung": eintrag["latein"],
            "pruefer": pruefe,
        }

    def _eingabetaste(self):
        if self.phase == "frage":
            self._pruefen()
        else:
            self._naechste()

    def _pruefen(self):
        antwort = self.antwort_feld.get().strip()
        bewertung, hinweis = self.frage["pruefer"](antwort)
        gruppe, eintrag = self.aufgaben[self.nummer]
        self.zaehler[bewertung] += 1
        self.app.statistik.buchen(gruppe, eintrag, bewertung)
        merker = ""
        if bewertung == quiz.FALSCH:
            self.urteil.configure(text="✗  Falsch", foreground=ROT)
            self.fehler_eintraege.append(eintrag)
            v = self.app.fehler.falsch(gruppe, eintrag)
            merker = (f"Kommt in die Fehlerliste: {self.app.fehler.fortschritt(v)}   "
                      f"({v['falsch']}× falsch)")
        else:
            self.punkte += 1
            if bewertung == quiz.PERFEKT:
                self.urteil.configure(text="★  Perfekt", foreground=GRUEN)
            else:
                self.urteil.configure(text="✓  Richtig", foreground=GRUEN)
            # Punkt gutschreiben, falls die Vokabel in der Fehlerliste steht
            v, geschafft = self.app.fehler.richtig(gruppe, eintrag)
            if geschafft:
                merker = "Geschafft – diese Vokabel ist jetzt aus der Fehlerliste raus."
            elif v:
                merker = (f"Fehlerliste: {self.app.fehler.fortschritt(v)}   "
                          f"noch {FD.ZIEL_PUNKTE - v['punkte']}× richtig")
        self.merker_text.configure(text=merker)
        # Die vollstaendige Loesung kommt immer, auch wenn die Antwort stimmt.
        self.loesung_text.configure(text=f"Lösung:  {self.frage['loesung']}",
                                    foreground=TEXT)
        self.formen_text.configure(text=quiz.stammformen(gruppe, eintrag))
        self.hinweis_text.configure(text=hinweis or "")
        self.antwort_feld.configure(state="disabled")
        self.pruef_knopf.configure(text="Weiter  (Enter oder Leertaste)")
        self.pruef_knopf.focus_set()
        self.nummer += 1
        self.phase = "antwort"
        # Zaehler sofort nachziehen, sonst steht oben noch der alte Punktestand
        self._fortschritt_zeigen()
        self.app._fuss_auffrischen()

    def _fortschritt_zeigen(self):
        z = self.zaehler
        self.fortschritt_text.configure(
            text=f"Frage {self.nummer} von {len(self.aufgaben)}   ·   "
                 f"★ {z[quiz.PERFEKT]} perfekt   ✓ {z[quiz.RICHTIG]} richtig   "
                 f"✗ {z[quiz.FALSCH]} falsch")
        self.balken.configure(value=self.nummer)

    def _ergebnis(self):
        self.phase = "ende"
        gestellt = self.nummer
        z = self.zaehler
        prozent = round(100 * self.punkte / gestellt) if gestellt else 0
        self.ergebnis_text.configure(
            text=f"{self.punkte} von {gestellt} richtig   ({prozent} %)",
            foreground=GRUEN if prozent >= 80 else ROT if prozent < 50 else TEXT)
        s = self.app.statistik.zahlen()
        self.ergebnis_unter.configure(
            text=f"★ {z[quiz.PERFEKT]} perfekt   ·   ✓ {z[quiz.RICHTIG]} richtig   ·   "
                 f"✗ {z[quiz.FALSCH]} falsch\n"
                 f"Insgesamt gelernt: {s['einzelne']} einzelne Vokabeln  ·  "
                 f"{s['abfragen']} Abfragen  "
                 f"(★ {s['perfekt']}  ✓ {s['richtig']}  ✗ {s['falsch']})")
        self.fehler_liste.delete(0, "end")
        for e in self.fehler_eintraege:
            self.fehler_liste.insert("end", f"  {e['latein']:<26} {e['deutsch']}")
        self._zeige(self.ansicht_ergebnis)


# --------------------------------------------------------------------------
#  Fehlerliste
# --------------------------------------------------------------------------

class FehlerReiter(ttk.Frame):
    """Zeigt die gesammelten Fehlervokabeln und übt nur diese."""

    def __init__(self, master, app):
        super().__init__(master, padding=14)
        self.app = app
        self.db = app.db
        self.fehler = app.fehler
        self.zeigt_archiv = False

        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        self.ueberschrift = ttk.Label(self, text="", font=schrift(16, "bold"))
        self.ueberschrift.grid(row=0, column=0, sticky="w")
        self.unterzeile = ttk.Label(self, text="", foreground=GRAU, font=schrift(10),
                                    justify="left")
        self.unterzeile.grid(row=1, column=0, sticky="w", pady=(4, 12))

        knoepfe = ttk.Frame(self)
        knoepfe.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        self.ueben_knopf = ttk.Button(knoepfe, text="Diese Vokabeln üben",
                                      command=self._ueben)
        self.ueben_knopf.pack(side="left", ipadx=14, ipady=4)
        self.richtung = tk.StringVar(value="ld")
        ttk.Radiobutton(knoepfe, text="La→De", value="ld",
                        variable=self.richtung).pack(side="left", padx=(12, 0))
        ttk.Radiobutton(knoepfe, text="De→La", value="dl",
                        variable=self.richtung).pack(side="left")
        ttk.Radiobutton(knoepfe, text="gemischt", value="mix",
                        variable=self.richtung).pack(side="left")
        self.archiv_knopf = ttk.Button(knoepfe, text="Archiv anzeigen",
                                       command=self._archiv_umschalten)
        self.archiv_knopf.pack(side="right")

        spalten = ("fortschritt", "latein", "deutsch", "lektion", "bilanz")
        self.tabelle = ttk.Treeview(self, columns=spalten, show="headings", selectmode="browse")
        self.SPALTEN = (("fortschritt", "Fortschritt", "center"),
                        ("latein", "Vokabel", "w"),
                        ("deutsch", "Bedeutung", "w"),
                        ("lektion", "Lektion", "center"),
                        ("bilanz", "falsch / richtig", "center"))
        for spalte, titel, anker in self.SPALTEN:
            # Ueberschrift genauso ausrichten wie die Spalte darunter - sonst
            # steht sie in einer breiten Spalte weit neben ihrem Inhalt.
            self.tabelle.heading(spalte, text=titel, anchor=anker)
            self.tabelle.column(spalte, width=px(120), minwidth=px(50), anchor=anker,
                                stretch=(spalte == "deutsch"))
        self.spalten_gesetzt = False
        self.tabelle.grid(row=3, column=0, sticky="nsew")
        leiste = ttk.Scrollbar(self, orient="vertical", command=self.tabelle.yview)
        leiste.grid(row=3, column=1, sticky="ns")
        self.tabelle.configure(yscrollcommand=leiste.set)
        self.tabelle.bind("<Double-Button-1>", self._nachschlagen)

        unten = ttk.Frame(self)
        unten.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(unten, text="Auf 0 zurücksetzen",
                   command=self._zuruecksetzen).pack(side="left")
        ttk.Button(unten, text="Aus der Liste nehmen",
                   command=self._entfernen).pack(side="left", padx=(8, 0))
        ttk.Label(unten, text="Doppelklick schlägt die Vokabel in der Suche nach.",
                  foreground=GRAU, font=schrift(9)).pack(side="right")
        umbruch_koppeln(self, [self.unterzeile])

        self.aktualisieren()

    def neu_skalieren(self):
        """Nach einer Groessenaenderung passen die Spalten nicht mehr - sie
        sind aus der Textbreite gerechnet, und die Schrift ist gewachsen."""
        self.spalten_gesetzt = False
        self.aktualisieren()

    # -------------------------------------------------- Anzeige
    def aktualisieren(self):
        zahlen = self.fehler.zahlen()
        self.ueberschrift.configure(
            text="Geschaffte Vokabeln" if self.zeigt_archiv else "Meine Fehlervokabeln")
        if self.zeigt_archiv:
            self.unterzeile.configure(
                text=f"{zahlen['geschafft']} Vokabeln geschafft.  "
                     f"Wer wieder darauf hereinfällt, findet sie mit ihrer Bilanz zurück "
                     f"in der Übung.")
        else:
            self.unterzeile.configure(
                text=f"{zahlen['offen']} in Übung  ·  {zahlen['geschafft']} geschafft  ·  "
                     f"{FD.ZIEL_PUNKTE}× richtig und eine Vokabel ist raus "
                     f"(falsch kostet einen Punkt)")
        self.archiv_knopf.configure(
            text="Zur Übung" if self.zeigt_archiv else "Archiv anzeigen")

        self.tabelle.delete(*self.tabelle.get_children())
        self.zeilen = self.fehler.archiv() if self.zeigt_archiv else self.fehler.aktive()
        werte = []
        for k, v in self.zeilen:
            reihe = (self.fehler.fortschritt(v), v["latein"], v["deutsch"],
                     v["lektion"], f"{v['falsch']} / {v['richtig']}")
            werte.append(reihe)
            self.tabelle.insert("", "end", iid=k, values=reihe)
        if not self.spalten_gesetzt and werte:
            self.spalten_gesetzt = True
            spalten_anpassen(self.tabelle, [(s[0], s[1]) for s in self.SPALTEN],
                             werte, dehnbar=("deutsch",))
        leer = not self.zeilen
        self.ueben_knopf.configure(state="disabled" if leer or self.zeigt_archiv else "normal")
        if leer:
            self.tabelle.insert("", "end", values=(
                "", "—",
                "Noch nichts gesammelt." if not self.zeigt_archiv
                else "Noch keine Vokabel geschafft.", "", ""))

    def _archiv_umschalten(self):
        self.zeigt_archiv = not self.zeigt_archiv
        self.aktualisieren()

    def _gewaehlt(self):
        wahl = self.tabelle.selection()
        return wahl[0] if wahl and wahl[0] in self.fehler.vokabeln else None

    # -------------------------------------------------- Aktionen
    def _ueben(self):
        paare = self.fehler.paare(self.db)
        if not paare:
            messagebox.showinfo("Fehlerliste",
                                "In der Liste steht keine Vokabel, die es in der "
                                "Vokabeldatei noch gibt.")
            return
        self.app.reiter.select(self.app.quiz)
        self.app.quiz.starte_mit(paare, modus=self.richtung.get())

    def _zuruecksetzen(self):
        k = self._gewaehlt()
        if k:
            self.fehler.zuruecksetzen(k)
            self.aktualisieren()

    def _entfernen(self):
        k = self._gewaehlt()
        if not k:
            return
        name = self.fehler.vokabeln[k]["latein"]
        if messagebox.askyesno("Aus der Liste nehmen",
                               f"„{name}“ ganz aus der Fehlerliste entfernen?\n\n"
                               f"Die Vokabel kommt erst wieder hinein, wenn du sie "
                               f"erneut falsch beantwortest."):
            self.fehler.entfernen(k)
            self.aktualisieren()

    def _nachschlagen(self, _ereignis=None):
        k = self._gewaehlt()
        if k:
            self.app.zur_suche(self.fehler.vokabeln[k]["latein"])


# --------------------------------------------------------------------------
#  Grammatik
# --------------------------------------------------------------------------

class GrammatikReiter(ttk.Frame):
    """Zeigt Formentabellen - je Lektion oder nach Thema."""

    def __init__(self, master, app):
        super().__init__(master, padding=14)
        self.app = app
        self.db = app.db
        self.neu = GR.neu_je_lektion(self.db)
        self.themen = GR.themen(self.db)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        kopf = ttk.Frame(self)
        kopf.grid(row=0, column=0, sticky="ew")
        kopf.columnconfigure(4, weight=1)      # leere Spalte rechts nimmt den Rest
        ttk.Label(kopf, text="Thema:", font=schrift(10)).grid(row=0, column=0, padx=(0, 8))
        self.wahl = ttk.Combobox(kopf, state="readonly", font=schrift(11), width=38,
                                 values=[n for n, _s in self.themen])
        self.wahl.current(0)
        self.wahl.grid(row=0, column=1, sticky="w", ipady=2)
        self.wahl.bind("<<ComboboxSelected>>", lambda _e: self.zeigen())
        ttk.Button(kopf, text="◀", width=3,
                   command=lambda: self._blaettern(-1)).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(kopf, text="▶", width=3,
                   command=lambda: self._blaettern(1)).grid(row=0, column=3, padx=(4, 0))

        zweite = ttk.Frame(self)
        zweite.grid(row=1, column=0, sticky="ew", pady=(6, 10))
        zweite.columnconfigure(0, weight=1)

        self.ansicht = tk.StringVar(value="tabellen")
        umschalter = ttk.Frame(zweite)
        umschalter.grid(row=0, column=1, sticky="e", padx=(12, 0))
        ttk.Radiobutton(umschalter, text="Tabellen", value="tabellen",
                        variable=self.ansicht, command=self.zeigen).pack(side="left")
        self.seiten_knopf = ttk.Radiobutton(umschalter, text="Buchseiten", value="seiten",
                                            variable=self.ansicht, command=self.zeigen)
        self.seiten_knopf.pack(side="left", padx=(10, 0))

        self.hinweis = ttk.Label(zweite, foreground=GRAU, font=schrift(9),
                                 justify="left", text="")
        self.hinweis.grid(row=0, column=0, sticky="w")
        umbruch_koppeln(self, [self.hinweis], rand=320)

        rahmen = ttk.Frame(self)
        rahmen.grid(row=2, column=0, sticky="nsew")
        rahmen.columnconfigure(0, weight=1)
        rahmen.rowconfigure(0, weight=1)
        self.ausgabe = tk.Text(rahmen, wrap="none", font=schrift(11, familie=MONO), padx=14, pady=12,
                               width=20, height=8, relief="flat", borderwidth=1, highlightthickness=1,
                               highlightbackground=RAND, highlightcolor=RAND,
                               state="disabled", background=KARTE, foreground=TEXT)
        self.ausgabe.grid(row=0, column=0, sticky="nsew")
        senk = ttk.Scrollbar(rahmen, orient="vertical", command=self.ausgabe.yview)
        senk.grid(row=0, column=1, sticky="ns")
        waag = ttk.Scrollbar(rahmen, orient="horizontal", command=self.ausgabe.xview)
        waag.grid(row=1, column=0, sticky="ew")
        self.ausgabe.configure(yscrollcommand=senk.set, xscrollcommand=waag.set)
        self.ausgabe.tag_configure("titel", font=schrift(13, "bold"), foreground=BLAU,
                                   spacing1=10, spacing3=4)
        self.ausgabe.tag_configure("tabelle", font=schrift(11, familie=MONO))
        self.ausgabe.tag_configure("leise", font=schrift(10), foreground=GRAU)
        self.ausgabe.tag_configure("warnung", font=schrift(13, "bold"), foreground=ROT,
                                   spacing1=10, spacing3=4)
        self.tabellen_rahmen = rahmen

        # --- Buchseiten: scrollbare Fläche mit den Fotos ---
        self.bild_rahmen = ttk.Frame(self)
        self.bild_rahmen.columnconfigure(0, weight=1)
        self.bild_rahmen.rowconfigure(0, weight=1)
        self.leinwand = tk.Canvas(self.bild_rahmen, background=FLAECHE,
                                  highlightthickness=1, highlightbackground=RAND)
        self.leinwand.grid(row=0, column=0, sticky="nsew")
        bildleiste = ttk.Scrollbar(self.bild_rahmen, orient="vertical",
                                   command=self.leinwand.yview)
        bildleiste.grid(row=0, column=1, sticky="ns")
        self.leinwand.configure(yscrollcommand=bildleiste.set)
        self.leinwand.bind("<Configure>", self._leinwand_veraendert)
        self.leinwand.bind("<MouseWheel>",
                           lambda e: self.leinwand.yview_scroll(-e.delta // 120, "units"))
        self.bilder = []          # Verweise halten, sonst raeumt Tk sie weg
        self._bild_timer = None
        self._letzte_breite = 0
        self.zeigen()

    # -------------------------------------------------- Buchseiten
    def _leinwand_veraendert(self, ereignis):
        if abs(ereignis.width - self._letzte_breite) < px(20):
            return
        self._letzte_breite = ereignis.width
        if self._bild_timer:
            self.after_cancel(self._bild_timer)
        self._bild_timer = self.after(150, self._seiten_zeichnen)

    def _seiten_zeichnen(self):
        self._bild_timer = None
        self.leinwand.delete("all")
        self.bilder = []
        seiten = self._seiten()
        breite = max(px(200), self.leinwand.winfo_width() - px(24))
        if not seiten:
            self.leinwand.create_text(20, 20, anchor="nw", fill=GRAU,
                                      font=schrift(11),
                                      text="Zu dieser Lektion sind keine Buchseiten "
                                           "hinterlegt.")
            self.leinwand.configure(scrollregion=(0, 0, 0, 0))
            return
        if Image is None:
            self.leinwand.create_text(
                20, 20, anchor="nw", fill=ROT, font=schrift(11), width=breite,
                text=("Zum Anzeigen der Buchseiten fehlt das Paket Pillow.\n"
                      "Installieren mit:   py -3 -m pip install pillow\n\n"
                      "Die Bilder liegen im Ordner grammatik_bilder und lassen sich "
                      "auch direkt öffnen."))
            self.leinwand.configure(scrollregion=(0, 0, 0, 0))
            return
        y = px(12)
        rand = px(12)
        gesamtbreite = breite
        for pfad in seiten:
            try:
                bild = Image.open(pfad)
            except OSError:
                continue
            # Die Fotos sind 1500 Pixel breit.  Auf einem grossen Bildschirm
            # waeren sie damit eine schmale Spalte in der Mitte, also darf das
            # Bild etwas ueber seine eigene Aufloesung hinaus - aber nur so
            # weit, dass die Schrift darauf noch scharf aussieht.
            bildfaktor = min(VERGROESSERUNG_MAX, breite / bild.width)
            neu = bild.resize((max(1, int(bild.width * bildfaktor)),
                               max(1, int(bild.height * bildfaktor))), Image.LANCZOS)
            foto = ImageTk.PhotoImage(neu)
            self.bilder.append(foto)
            # mittig setzen, sonst kleben schmale Seiten am linken Rand
            x = max(rand, (breite - neu.width) // 2 + rand)
            self.leinwand.create_image(x, y, anchor="nw", image=foto)
            gesamtbreite = max(gesamtbreite, x + neu.width + rand)
            y += neu.height + px(16)
        self.leinwand.configure(scrollregion=(0, 0, gesamtbreite, y))

    def _seiten(self):
        _name, schluessel = self.themen[self.wahl.current()]
        if schluessel[0] != "lektion":
            return []
        return GR.buchseiten(schluessel[1])

    def _blaettern(self, richtung):
        i = max(0, min(len(self.themen) - 1, self.wahl.current() + richtung))
        self.wahl.current(i)
        self.zeigen()

    def neu_skalieren(self):
        self._letzte_breite = 0
        if self.ansicht.get() == "seiten":
            self._seiten_zeichnen()

    def zeigen(self):
        _name, schluessel = self.themen[self.wahl.current()]
        seiten = self._seiten()
        self.seiten_knopf.configure(state="normal" if seiten else "disabled")
        if not seiten and self.ansicht.get() == "seiten":
            self.ansicht.set("tabellen")

        if self.ansicht.get() == "seiten":
            self.tabellen_rahmen.grid_forget()
            self.bild_rahmen.grid(row=2, column=0, sticky="nsew")
            nachziehen_bald(self)
            self.hinweis.configure(
                text=f"{len(seiten)} Seite{'n' if len(seiten) != 1 else ''} aus dem "
                     f"Lehrbuch.  Mit dem Mausrad scrollen.")
            self._letzte_breite = 0
            self.after(50, self._seiten_zeichnen)
            return

        self.bild_rahmen.grid_forget()
        self.tabellen_rahmen.grid(row=2, column=0, sticky="nsew")
        ungeprueft = schluessel[0] == "lektion" and GR.ist_ungeprueft(schluessel[1])
        if ungeprueft:
            self.hinweis.configure(
                foreground=ROT,
                text=f"⚠  Zu Lektion {schluessel[1]} liegt keine Grammatikseite aus dem "
                     f"Buch vor – die Themen sind nur aus den Vokabeln abgeleitet und "
                     f"können vom Lehrbuch abweichen.")
        else:
            self.hinweis.configure(
                foreground=GRAU,
                text="Die Tabellen werden aus den Vokabeln erzeugt – ohne Längenzeichen, "
                     "weil die Formen aus dem Wortstamm gebildet werden."
                     + ("   Für diese Lektion gibt es auch Buchseiten." if seiten else ""))
        tafeln = GR.tafeln(self.db, schluessel, self.neu)
        self.ausgabe.configure(state="normal")
        self.ausgabe.delete("1.0", "end")
        if not tafeln:
            self.ausgabe.insert("end", "Zu diesem Thema gibt es keine Tabellen.\n", "leise")
        for tafel in tafeln:
            zeilen = tafel.text().splitlines()
            # Der Warnblock einer ungeprüften Lektion wird rot gesetzt
            marke = "warnung" if zeilen[0].startswith("⚠") else "titel"
            self.ausgabe.insert("end", zeilen[0] + "\n", marke)
            self.ausgabe.insert("end", "\n".join(zeilen[1:]) + "\n\n", "tabelle")
        self.ausgabe.configure(state="disabled")
        self.ausgabe.yview_moveto(0)
        self.ausgabe.xview_moveto(0)


# --------------------------------------------------------------------------
#  Alle Vokabeln
# --------------------------------------------------------------------------

class VokabelnReiter(ttk.Frame):
    """Einfache Liste aller Vokabeln in ihrer Grundform, sortier- und filterbar."""

    SPALTEN = (("lektion", "Lektion", 70, "center"),
               ("latein", "Vokabel", 150, "w"),
               ("wortart", "Wortart", 90, "w"),
               ("deutsch", "Bedeutung", 220, "w"),
               ("formen", "Formen", 180, "w"))

    def __init__(self, master, app):
        super().__init__(master, padding=14)
        self.app = app
        self.db = app.db
        self.sortiert_nach = "lektion"
        self.absteigend = False

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        kopf = ttk.Frame(self)
        kopf.grid(row=0, column=0, sticky="ew")
        kopf.columnconfigure(3, weight=1)

        ttk.Label(kopf, text="Lektion:", font=schrift(10)).grid(row=0, column=0)
        self.lektion_wahl = ttk.Combobox(kopf, state="readonly", width=10, font=schrift(10),
                                         values=["alle"] + [str(n) for n in self.lektionen()])
        self.lektion_wahl.current(0)
        self.lektion_wahl.grid(row=0, column=1, padx=(6, 18))
        self.lektion_wahl.bind("<<ComboboxSelected>>", lambda _e: self.fuellen())

        ttk.Label(kopf, text="Suchen:", font=schrift(10)).grid(row=0, column=2)
        self.filter_feld = ttk.Entry(kopf, font=schrift(11))
        self.filter_feld.grid(row=0, column=3, sticky="ew", padx=(6, 12), ipady=2)
        self.filter_feld.bind("<KeyRelease>", lambda _e: self.fuellen())
        ttk.Button(kopf, text="Zurücksetzen", command=self._leeren).grid(row=0, column=4)

        self.zeile_info = ttk.Label(self, text="", foreground=GRAU, font=schrift(9))
        self.zeile_info.grid(row=1, column=0, sticky="w", pady=(6, 8))

        self.tabelle = ttk.Treeview(self, columns=[s[0] for s in self.SPALTEN],
                                    show="headings", selectmode="browse")
        for name, titel, breite, anker in self.SPALTEN:
            self.tabelle.heading(name, text=titel, anchor=anker,
                                 command=lambda n=name: self._sortieren(n))
            self.tabelle.column(name, width=px(breite), minwidth=px(50), anchor=anker,
                                stretch=(name in ("deutsch", "formen")))
        self.spalten_gesetzt = False
        self.tabelle.grid(row=2, column=0, sticky="nsew")
        leiste = ttk.Scrollbar(self, orient="vertical", command=self.tabelle.yview)
        leiste.grid(row=2, column=1, sticky="ns")
        self.tabelle.configure(yscrollcommand=leiste.set)
        self.tabelle.bind("<Double-Button-1>", self._nachschlagen)

        fusshinweis = ttk.Label(self, foreground=GRAU, font=schrift(9), justify="left",
                                text="Klick auf eine Überschrift sortiert.  Doppelklick "
                                     "auf eine Zeile schlägt sie in der Suche nach.")
        fusshinweis.grid(row=3, column=0, sticky="w", pady=(6, 0))
        umbruch_koppeln(self, [fusshinweis])
        self.fuellen()

    def lektionen(self):
        return sorted({e["lektion"] for e in self.db.entries})

    # -------------------------------------------------- Daten
    def _zeilen(self):
        gewaehlt = self.lektion_wahl.get()
        nur = None if gewaehlt == "alle" else int(gewaehlt)
        text = self.filter_feld.get().strip().lower()
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
                               "formen": quiz.stammformen(g, e), "gid": g["id"],
                               "roh": e["latein"]})
        return zeilen

    def _schluessel(self, z):
        if self.sortiert_nach == "lektion":
            return (z["lektion"], norm(z["latein"]))
        if self.sortiert_nach == "latein":
            return (norm(z["latein"]), z["lektion"])
        if self.sortiert_nach == "deutsch":
            return (z["deutsch"].lower(), z["lektion"])
        if self.sortiert_nach == "wortart":
            ordnung = (WORTART_ORDER.index(z["wortart"])
                       if z["wortart"] in WORTART_ORDER else 99)
            return (ordnung, z["lektion"], norm(z["latein"]))
        return (z["formen"].lower(), z["lektion"])

    def neu_skalieren(self):
        self.spalten_gesetzt = False
        self.fuellen()

    def fuellen(self):
        zeilen = sorted(self._zeilen(), key=self._schluessel, reverse=self.absteigend)
        self.tabelle.delete(*self.tabelle.get_children())
        self.daten = zeilen
        for i, z in enumerate(zeilen):
            self.tabelle.insert("", "end", iid=str(i),
                                values=(z["lektion"], z["latein"], z["wortart"],
                                        z["deutsch"], z["formen"]))
        pfeil = "▼" if self.absteigend else "▲"
        namen = {s[0]: s[1] for s in self.SPALTEN}
        for name, titel, _b, _a in self.SPALTEN:
            self.tabelle.heading(name, text=titel + ("  " + pfeil
                                                     if name == self.sortiert_nach else ""),
                                 anchor=dict((s[0], s[3]) for s in self.SPALTEN)[name])
        if not self.spalten_gesetzt and zeilen:
            self.spalten_gesetzt = True
            spalten_anpassen(
                self.tabelle, [(s[0], s[1]) for s in self.SPALTEN],
                [(z["lektion"], z["latein"], z["wortart"], z["deutsch"], z["formen"])
                 for z in zeilen],
                dehnbar=("deutsch", "formen"))
        gesamt = len(self.db.entries)
        self.zeile_info.configure(
            text=f"{len(zeilen)} von {gesamt} Vokabeln  ·  sortiert nach "
                 f"{namen[self.sortiert_nach]}")

    def _sortieren(self, spalte):
        if spalte == self.sortiert_nach:
            self.absteigend = not self.absteigend
        else:
            self.sortiert_nach, self.absteigend = spalte, False
        self.fuellen()

    def _leeren(self):
        self.filter_feld.delete(0, "end")
        self.lektion_wahl.current(0)
        self.fuellen()

    def _nachschlagen(self, _ereignis=None):
        wahl = self.tabelle.selection()
        if not wahl:
            return
        z = self.daten[int(wahl[0])]
        self.app.zur_suche(z["roh"])


# --------------------------------------------------------------------------
#  Hauptfenster
# --------------------------------------------------------------------------

def dpi_beachten():
    """Windows skaliert das Fenster sonst selbst: die Schrift wird unscharf und
    die Groessenangaben stimmen nicht mehr mit den Bildschirmpixeln ueberein.
    Muss laufen, bevor das erste Fenster entsteht."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


class VokabelApp(tk.Tk):
    def __init__(self):
        dpi_beachten()
        super().__init__()
        self.title("Latein – Vokabeln")

        # Nach der DPI-Umstellung rechnet Tk in echten Pixeln - die Schrift
        # muss dann selbst mitwachsen, sonst wird sie winzig.
        try:
            self.tk.call("tk", "scaling", self.winfo_fpixels("1i") / 72.0)
        except Exception:
            pass
        einheit_bestimmen(self)
        # Knapper geht es nicht: das Quiz-Einstellungsbild mit den
        # Formen-Optionen ist der hoechste Inhalt und braucht diesen Platz.
        self.minsize(dp(REF_BREITE - 80), dp(REF_HOEHE - 20))

        # Erst die Fenstergroesse festlegen, dann daraus den Faktor - sonst
        # wuerde alles einmal in der falschen Groesse aufgebaut und flackert.
        breite, hoehe = self._mittig()
        faktor_setzen(faktor_fuer(breite, hoehe))
        self._skalier_timer = None

        self.stil = stil_einrichten(self)

        try:
            self.db = VokabelBase()
        except FileNotFoundError:
            messagebox.showerror("Vokabeldatei fehlt",
                                 f"Die Vokabeldatei wurde nicht gefunden:\n{DB_PATH}")
            self.destroy()
            raise SystemExit(1)

        self.fehler = FD.FehlerListe()
        self.statistik = FD.Statistik()

        fusszeile = ttk.Frame(self)
        fusszeile.pack(side="bottom", fill="x", padx=16, pady=(0, 8))
        self.fuss = masse(ttk.Label(fusszeile, foreground=GRAU, font=schrift(9),
                                    justify="left"),
                          wraplength=900)
        self.fuss.pack(side="left")
        ttk.Label(fusszeile, text="created by bj", foreground=BLASS,
                  font=schrift(9)).pack(side="right")

        self.reiter = ttk.Notebook(self)
        self.reiter.pack(fill="both", expand=True, padx=10, pady=10)
        self.suche = SuchReiter(self.reiter, self)
        self.quiz = QuizReiter(self.reiter, self)
        self.fehler_reiter = FehlerReiter(self.reiter, self)
        self.grammatik = GrammatikReiter(self.reiter, self)
        self.vokabeln = VokabelnReiter(self.reiter, self)
        self.reiter.add(self.suche, text="   Suche   ")
        self.reiter.add(self.quiz, text="   Quiz   ")
        self.reiter.add(self.fehler_reiter, text="   Fehlervokabeln   ")
        self.reiter.add(self.grammatik, text="   Grammatik   ")
        self.reiter.add(self.vokabeln, text="   Alle Vokabeln   ")
        # Die Liste kann sich im Quiz geändert haben
        self.reiter.bind("<<NotebookTabChanged>>", self._reiter_gewechselt)

        for titel, warnung in (("Fehlerliste", self.fehler.warnung),
                               ("Statistik", self.statistik.warnung)):
            if warnung:
                messagebox.showwarning(titel, warnung)

        self._fuss_auffrischen()

        self.bind("<Control-f>", lambda _e: self.zur_suche())
        self.bind("<Control-q>", lambda _e: self.reiter.select(self.quiz))
        self.protocol("WM_DELETE_WINDOW", self._schliessen)
        abstaende_nachziehen(self)
        self.bind("<Configure>", self._groesse_geaendert)
        self.suche.eingabe.focus_set()

    # -------------------------------------------------- Mitwachsen
    def _groesse_geaendert(self, ereignis):
        """Beim Ziehen am Fensterrand kommen Dutzende Meldungen - erst kurz
        abwarten, sonst wird bei jedem Pixel neu gerechnet."""
        if ereignis.widget is not self:
            return
        if self._skalier_timer is not None:
            self.after_cancel(self._skalier_timer)
        self._skalier_timer = self.after(120, self._skalierung_pruefen)

    def _skalierung_pruefen(self):
        self._skalier_timer = None
        if not faktor_setzen(faktor_fuer(self.winfo_width(), self.winfo_height())):
            return
        stil_masse(self.stil)
        abstaende_nachziehen(self)
        neu_vermessen()
        for reiter in (self.suche, self.quiz, self.fehler_reiter,
                       self.grammatik, self.vokabeln):
            nachziehen = getattr(reiter, "neu_skalieren", None)
            if nachziehen is not None:
                nachziehen()

    def _reiter_gewechselt(self, _ereignis=None):
        if self.reiter.select() == str(self.fehler_reiter):
            self.fehler_reiter.aktualisieren()
        self._fuss_auffrischen()

    def _fuss_auffrischen(self):
        zahlen = self.fehler.zahlen()
        s = self.statistik.zahlen()
        self.fuss.configure(
            text=f"{len(self.db.entries)} Vokabeln  ·  "
                 f"{len(self.db.form_index)} erkannte Formen  ·  "
                 f"{zahlen['offen']} in Übung  ·  "
                 f"gelernt: {s['einzelne']} einzelne / {s['abfragen']} Abfragen")

    def _schliessen(self):
        # Gespeichert wird zwar nach jeder Antwort, aber sicher ist sicher.
        self.fehler.speichern()
        self.destroy()

    def zur_suche(self, wort=None):
        self.reiter.select(self.suche)
        if wort:
            self.suche.suche_mit(wort)
        else:
            self.suche.eingabe.focus_set()

    def _mittig(self):
        """Startgroesse und -platz.  Die Zahlen sind Design-Pixel, damit das
        Fenster auf einem 4K-Schirm nicht als Briefmarke aufgeht."""
        self.update_idletasks()
        schirm_b, schirm_h = self.winfo_screenwidth(), self.winfo_screenheight()
        breite = min(dp(1240), int(schirm_b * 0.68))
        hoehe = min(dp(880), int(schirm_h * 0.80))
        x = (schirm_b - breite) // 2
        y = (schirm_h - hoehe) // 3
        self.geometry(f"{breite}x{hoehe}+{max(0, x)}+{max(0, y)}")
        return breite, hoehe


def selbsttest():
    """Schreibt eine Datei mit allen Pfaden neben das Programm und beendet sich.

    Aufruf:  Latein_Vokabeltrainer.exe --pfade
    Nützlich, wenn auf einem fremden Rechner etwas nicht gefunden wird - in der
    gepackten .exe gibt es kein Konsolenfenster, in dem man nachsehen könnte.
    """
    pfade.lernstand_bereitstellen()
    bericht = [
        "Latein-Vokabeltrainer – Pfade",
        "=" * 34,
        f"läuft als .exe    : {pfade.ALS_EXE}",
        f"Programmordner    : {pfade.BASIS}",
        f"mitgelieferte Daten: {pfade.MITGELIEFERT}",
        f"Daten             : {pfade.DATEN}",
        f"Lernstand         : {pfade.LERNSTAND}",
        "",
        f"Vokabeldatei      : {pfade.VOKABELDATEI}  "
        f"({'gefunden' if pfade.VOKABELDATEI.is_file() else 'FEHLT'})",
        f"Buchseiten        : {pfade.GRAMMATIK_BILDER}  "
        f"({len(list(pfade.GRAMMATIK_BILDER.glob('*.jpg'))) if pfade.GRAMMATIK_BILDER.is_dir() else 'FEHLT'})",
        f"Fehlerliste       : {pfade.FEHLERLISTE}",
        f"Statistik         : {pfade.STATISTIK}",
        f"Pillow (Bilder)   : {'vorhanden' if Image else 'fehlt'}",
    ]
    ziel = pfade.LERNSTAND / "pfade.txt"
    try:
        ziel.write_text("\n".join(bericht) + "\n", encoding="utf-8")
    except OSError as ex:
        ziel = pfade.BASIS / "pfade.txt"
        bericht.append(f"(Lernstand-Ordner nicht beschreibbar: {ex})")
        ziel.write_text("\n".join(bericht) + "\n", encoding="utf-8")
    return ziel


def main():
    if "--pfade" in sys.argv[1:]:
        selbsttest()
        return
    app = VokabelApp()
    app.mainloop()


if __name__ == "__main__":
    main()
