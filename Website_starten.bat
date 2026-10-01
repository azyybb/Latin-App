@echo off
rem ===========================================================================
rem  Startet die Website ohne Docker:   http://127.0.0.1:8765
rem  Fuers Handy im selben WLAN vorher  set LATEIN_HOST=0.0.0.0  setzen und
rem  dann die IP-Adresse dieses PCs mit :8765 im Handy-Browser oeffnen.
rem  Lernstaende landen in lernstand\nutzer\ (je Lerncode ein Ordner).
rem ===========================================================================
setlocal
start "" http://127.0.0.1:8765/
py -3 "%~dp0programm\web_server.py"
pause
