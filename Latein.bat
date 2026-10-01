@echo off
rem ===========================================================================
rem  Startet die Vokabel-Oberflaeche per Doppelklick.
rem  Sucht Python der Reihe nach an mehreren Stellen, damit die Datei auch auf
rem  einem fremden Rechner laeuft, wo es den "pyw"-Launcher nicht gibt.
rem  "start" haengt das Fenster ab, damit diese Eingabeaufforderung sofort
rem  wieder verschwindet - sonst bliebe sie offen, solange das Programm laeuft.
rem ===========================================================================
setlocal
set "SKRIPT=%~dp0programm\vokabel_gui.py"

if not exist "%SKRIPT%" (
    echo.
    echo   programm\vokabel_gui.py wurde nicht gefunden.
    echo   Der Ordner "programm" muss neben dieser Datei liegen.
    echo.
    pause
    exit /b 1
)

rem --- 1) Launcher von python.org, startet ohne Konsolenfenster ---
where pyw >nul 2>&1
if not errorlevel 1 (
    start "" pyw -3 "%SKRIPT%"
    exit /b
)

rem --- 2) pythonw aus dem Suchpfad ---
where pythonw >nul 2>&1
if not errorlevel 1 (
    start "" pythonw "%SKRIPT%"
    exit /b
)

rem --- 3) uebliche Installationsorte durchsuchen ---
for %%V in (315 314 313 312 311 310 39) do (
    for %%O in (
        "%LOCALAPPDATA%\Programs\Python\Python%%V"
        "%ProgramFiles%\Python%%V"
        "C:\Python%%V"
    ) do (
        if exist "%%~O\pythonw.exe" (
            start "" "%%~O\pythonw.exe" "%SKRIPT%"
            exit /b
        )
    )
)

rem --- 4) notfalls python.exe, dann bleibt ein Konsolenfenster stehen ---
where python >nul 2>&1
if not errorlevel 1 (
    echo Starte ueber python.exe - dieses Fenster bitte offen lassen.
    python "%SKRIPT%"
    exit /b
)

echo.
echo   ============================================================
echo    Auf diesem Rechner wurde kein Python gefunden.
echo   ============================================================
echo.
echo    Entweder Python installieren:
echo      1. https://www.python.org/downloads/  oeffnen
echo      2. Python herunterladen und installieren
echo      3. Im Installationsfenster UNBEDINGT beide Haken setzen:
echo            [x] Add python.exe to PATH
echo            [x] py launcher
echo      4. Danach diese Datei wieder doppelklicken
echo.
echo    ODER die mitgelieferte Latein_Vokabeltrainer.exe benutzen -
echo    die braucht kein Python.
echo.
echo    Hinweis: Python aus dem Microsoft Store bringt den
echo    "py"-Launcher nicht mit - besser die Version von python.org.
echo.
pause
