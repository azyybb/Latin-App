"""
web_server.py  -  der Vokabeltrainer als Website
================================================
Dieselbe Oberflaeche wie die Handy-App (handy_oberflaeche.html), aber fuer
viele Besucher gleichzeitig: Jeder Browser bekommt einen Lerncode (Cookie)
und damit seine eigene Fehlerliste und Statistik unter

    lernstand/nutzer/<lerncode>/

Wer auf einem anderen Geraet weiterlernen will, gibt dort den Lerncode ein.
Dazu kommt die Arena (arena.py): Online-Quiz gegeneinander mit Raumcode.

    py -3 web_server.py            ->  http://127.0.0.1:8765

Im Docker-Betrieb (docker-compose.yml) steht nginx davor, liefert Seite und
Buchseiten selbst aus und reicht nur /api/ hierher weiter.

Umgebung:  LATEIN_HOST (127.0.0.1 - fuers WLAN/Docker 0.0.0.0), LATEIN_PORT (8765),
           LATEIN_DATEN / LATEIN_LERNSTAND wie in pfade.py
"""

import json
import os
import re
import secrets
import sys
import threading
import traceback
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import arena
import handy_server as HS
import pfade

NUTZER = pfade.LERNSTAND / "nutzer"
COOKIE = "latein_code"
COOKIE_DAUER = 2 * 365 * 24 * 3600
ZEICHEN = "abcdefghjkmnpqrstuvwxyz23456789"     # ohne 0/o, 1/l/i
CODE_LAENGE = 12
CODE_MUSTER = re.compile(f"^[{ZEICHEN}]{{{CODE_LAENGE}}}$")
IM_SPEICHER = 300                  # so viele Nutzer bleiben geladen
GROESSTE_ANFRAGE = 64 * 1024


def code_neu():
    while True:
        code = "".join(secrets.choice(ZEICHEN) for _ in range(CODE_LAENGE))
        if not bekannt(code):
            return code


def bekannt(code):
    """Hat dieser Code schon einen Lernstand (gespeichert oder gerade geladen)?"""
    return code in _trainer or (NUTZER / code).is_dir()


def code_lesen(text):
    """ABCD-EFGH-JKMN, abcd efgh jkmn, ... -> abcdefghjkmn  oder None."""
    code = re.sub(r"[^0-9a-z]", "", str(text or "").lower())
    return code if CODE_MUSTER.match(code) else None


def code_zeigen(code):
    return "-".join(code[i:i + 4] for i in range(0, len(code), 4)).upper()


# --------------------------------------------------------------------------
#  Nutzerverwaltung
# --------------------------------------------------------------------------

_bereit = threading.Event()
_sperre = threading.Lock()         # eine Anfrage nach der anderen, wie in handy_server
_grundlage = None
_ladefehler = None
_trainer = OrderedDict()           # code -> Trainer, zuletzt benutzte hinten


def _laden():
    global _grundlage, _ladefehler
    try:
        _grundlage = HS.Grundlage()
    except Exception:
        _ladefehler = traceback.format_exc()
    _bereit.set()


def trainer_fuer(code):
    """Nur unter _sperre aufrufen."""
    t = _trainer.get(code)
    if t is None:
        # Der Ordner entsteht erst beim ersten Speichern (fehler_datenbank.schreiben)
        t = _trainer[code] = HS.Trainer(_grundlage, NUTZER / code)
        while len(_trainer) > IM_SPEICHER:
            _trainer.popitem(last=False)
    _trainer.move_to_end(code)
    return t


def konto(code, _t, _d):
    return {"code": code_zeigen(code)}, None


def konto_wechseln(code, _t, d):
    neu = code_lesen(d.get("code"))
    if neu is None:
        return {"fehler": "Ein Lerncode hat 12 Zeichen, z. B. ABCD-EFGH-JKMN."}, None
    if not bekannt(neu):
        return {"fehler": "Diesen Lerncode gibt es nicht."}, None
    return {"code": code_zeigen(neu)}, neu


EXTRA = {"konto": konto, "konto/wechseln": konto_wechseln}

# Online-Quiz gegeneinander (arena.py)
ARENA = arena.Arena(trainer_fuer)
for _name, _aktion in ARENA.aktionen.items():
    EXTRA["arena/" + _name] = lambda code, t, d, _a=_aktion: (_a(code, t, d), None)


# --------------------------------------------------------------------------
#  Webserver
# --------------------------------------------------------------------------

class Anfrage(BaseHTTPRequestHandler):
    server_version = "LateinVokabeln"

    def log_message(self, *_args):
        pass

    def do_GET(self):
        url = urlparse(self.path)
        pfad = unquote(url.path)
        if pfad in ("/", "/index.html"):
            return self._senden(200, HS.OBERFLAECHE.read_bytes(), "text/html; charset=utf-8")
        if pfad == "/gesund":
            ok = _bereit.is_set() and not _ladefehler
            return self._senden(200 if ok else 503, b"ok" if ok else b"laedt", "text/plain")
        if pfad.startswith("/bild/"):
            name = pfad[len("/bild/"):]
            datei = pfade.GRAMMATIK_BILDER / name
            if Path(name).name != name or datei.suffix.lower() != ".jpg" or not datei.is_file():
                return self._senden(404, b"", "text/plain")
            return self._senden(200, datei.read_bytes(), "image/jpeg", zwischenspeichern=True)
        self._senden(404 if not pfad.startswith("/api/") else 405, b"", "text/plain")

    def do_POST(self):
        pfad = unquote(urlparse(self.path).path)
        if not pfad.startswith("/api/"):
            return self._senden(404, b"", "text/plain")
        laenge = int(self.headers.get("Content-Length") or 0)
        if laenge > GROESSTE_ANFRAGE:
            return self._json(413, {"absturz": "Anfrage zu groß."})
        daten = {}
        if laenge:
            try:
                daten = json.loads(self.rfile.read(laenge))
            except ValueError:
                daten = None
            if not isinstance(daten, dict):
                return self._json(400, {"absturz": "Ungültige Anfrage."})

        _bereit.wait()
        if _ladefehler:
            return self._json(500, {"absturz": "Die Vokabeln konnten nicht geladen werden.\n\n"
                                               + _ladefehler})
        name = pfad[len("/api/"):]
        try:
            with _sperre:
                code = code_lesen(self._cookie(COOKIE))
                if code is not None and not bekannt(code):
                    code = None            # nie gespeichert oder geloescht -> neu anfangen
                neuer_code = code is None
                code = code or code_neu()
                t = trainer_fuer(code)
                if name not in EXTRA and name not in t.aktionen:
                    return self._json(404, {"absturz": f"Unbekannt: {pfad}"})
                if name in EXTRA:
                    antwort, wechsel = EXTRA[name](code, t, daten)
                    if wechsel:
                        code, neuer_code = wechsel, True
                        trainer_fuer(code)
                else:
                    antwort = t.aktionen[name](daten)
                    if name == "start":
                        antwort["konto"] = code_zeigen(code)
        except Exception:
            return self._json(500, {"absturz": traceback.format_exc()})
        self._json(200, antwort, code if neuer_code else None)

    # -------------------------------------------------- Hilfen
    def _cookie(self, name):
        for teil in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = teil.strip().partition("=")
            if k == name:
                return v
        return None

    def _senden(self, status, inhalt, art, zwischenspeichern=False, kopf=()):
        self.send_response(status)
        self.send_header("Content-Type", art)
        self.send_header("Content-Length", str(len(inhalt)))
        self.send_header("Cache-Control", "max-age=86400" if zwischenspeichern else "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in kopf:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(inhalt)

    def _json(self, status, daten, code=None):
        kopf = []
        if code:
            kopf.append(("Set-Cookie", f"{COOKIE}={code}; Max-Age={COOKIE_DAUER}; Path=/; "
                                       f"HttpOnly; SameSite=Lax"))
        self._senden(status, json.dumps(daten, ensure_ascii=False).encode("utf-8"),
                     "application/json; charset=utf-8", kopf=kopf)


def main():
    host = os.environ.get("LATEIN_HOST", "127.0.0.1")
    port = int(os.environ.get("LATEIN_PORT", "8765"))
    pfade.lernstand_bereitstellen()
    NUTZER.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=_laden, daemon=True).start()
    server = ThreadingHTTPServer((host, port), Anfrage)
    server.daemon_threads = True
    print(f"Website laeuft:  http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port}/"
          f"   (Lernstaende in {NUTZER}, Beenden mit Strg+C)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())
