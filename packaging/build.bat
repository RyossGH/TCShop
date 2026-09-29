@echo off
rem Construit TCShop.exe puis l'installeur TCShop-Setup-x.y.z.exe (dans dist\installer)
setlocal
cd /d "%~dp0.."

echo [1/3] Icones...
".venv\Scripts\python.exe" tools\make_icon.py || goto :error

echo [2/3] Application (PyInstaller)...
".venv\Scripts\pyinstaller.exe" packaging\tcshop.spec --noconfirm --clean --distpath dist --workpath build || goto :error

echo [3/3] Installeur (Inno Setup)...
set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
    echo Inno Setup 6 introuvable : installez-le avec  winget install JRSoftware.InnoSetup
    goto :error
)
"%ISCC%" /Q packaging\tcshop.iss || goto :error

echo.
echo Termine : dist\installer
exit /b 0

:error
echo ECHEC de la construction.
exit /b 1
