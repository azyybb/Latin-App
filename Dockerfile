# syntax=docker/dockerfile:1
# ===========================================================================
#  Latein-Vokabeltrainer als Website - zwei Images aus einer Datei:
#
#    app   Python-Server (programm/web_server.py), nur Standardbibliothek
#    web   nginx: liefert Seite und Buchseiten selbst aus und reicht /api/
#          an "app" weiter
#
#  Gebaut und gestartet wird beides mit:   docker compose up -d --build
# ===========================================================================

# ---------------------------------------------------------------- app
FROM python:3.12-slim AS app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LATEIN_DATEN=/app/daten \
    LATEIN_LERNSTAND=/lernstand \
    LATEIN_HOST=0.0.0.0 \
    LATEIN_PORT=8765

RUN useradd --system --uid 10001 --no-create-home latein \
 && mkdir /lernstand && chown latein /lernstand

WORKDIR /app/programm
COPY daten/vokabel_base.json daten/saetze.txt /app/daten/
COPY daten/grammatik_bilder/ /app/daten/grammatik_bilder/
COPY programm/pfade.py programm/bettervokable_search.py programm/vokabel_search.py \
     programm/fehler_datenbank.py programm/grammatik.py programm/handy_server.py \
     programm/web_server.py programm/arena.py programm/saetze.py \
     programm/handy_oberflaeche.html ./

USER latein
VOLUME /lernstand
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/gesund', timeout=4)"
CMD ["python", "web_server.py"]

# ---------------------------------------------------------------- web
FROM nginx:1.27-alpine AS web

COPY webserver/nginx.conf /etc/nginx/conf.d/default.conf
COPY programm/handy_oberflaeche.html /usr/share/nginx/html/index.html
COPY daten/grammatik_bilder/ /usr/share/nginx/html/bild/

EXPOSE 80
