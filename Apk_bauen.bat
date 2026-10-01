@echo off
rem  Baut Latein_Vokabeltrainer.apk fuers Handy.
rem  Der erste Lauf laedt Java und das Android-SDK nach D:\LateinApp und
rem  dauert entsprechend lange; danach geht es in ein paar Minuten.
setlocal
py -3 "%~dp0programm\apk_bauen.py"
echo.
pause
