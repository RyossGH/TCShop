@echo off
rem Construit l'appli iPhone (Flutter web) et la range dans app\resources\webapp (servie par TCShop en HTTPS)
setlocal
cd /d "%~dp0"
call "C:\Users\Ryan Beaufrere\Documents\DEV\flutter\bin\flutter.bat" build web --release --base-href /app/ --pwa-strategy=none --no-web-resources-cdn || exit /b 1
"..\.venv\Scripts\python.exe" tool\make_web.py || exit /b 1
