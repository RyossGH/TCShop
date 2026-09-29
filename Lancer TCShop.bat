@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" goto run

echo Premiere installation de TCShop, patientez (1 a 2 minutes)...
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && python -c "import sys" >nul 2>nul && set "PY=python"
)
if not defined PY (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%D\python.exe" set "PY="%%D\python.exe""
)
if not defined PY (
    echo Python 3 est introuvable. Installez-le depuis https://www.python.org/downloads/ puis relancez.
    pause
    exit /b 1
)
%PY% -m venv .venv || (echo Echec de creation de l'environnement. & pause & exit /b 1)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || (echo Echec d'installation. & pause & exit /b 1)

:run
start "" ".venv\Scripts\pythonw.exe" main.py
