@echo off
rem ===========================================================================
rem  Packt das Programm als ZIP zum Verschicken (Ordner-Fassung, braucht Python).
rem  Wer kein Python mag, bekommt stattdessen Latein_Vokabeltrainer.exe.
rem  Die eigenen Lernstaende bleiben absichtlich draussen.
rem ===========================================================================
setlocal
where py >nul 2>&1
if errorlevel 1 (
    echo   Python wurde nicht gefunden - zum Packen wird es gebraucht.
    pause
    exit /b 1
)

py -3 "%~dp0programm\paket.py"
if errorlevel 1 (
    echo.
    echo   Das Packen ist fehlgeschlagen.
    pause
    exit /b 1
)
echo.
pause
