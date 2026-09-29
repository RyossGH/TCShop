@echo off
rem Construit TCShop Mobile (APK Android) et le copie dans dist\mobile
setlocal
set "SRC=%~dp0"
set "JAVA_HOME=C:\Program Files\Eclipse Adoptium\jdk-21.0.12.101-hotspot"
set "ANDROID_HOME=C:\Android\Sdk"
rem contournement Java/Windows « Unable to establish loopback connection » : dossier temporaire sans espace
if not exist C:\Android\tmp mkdir C:\Android\tmp
set "TMP=C:\Android\tmp"
set "TEMP=C:\Android\tmp"
set "JAVA_TOOL_OPTIONS=-Djdk.net.unixdomain.tmpdir=C:\Android\tmp -Djava.io.tmpdir=C:\Android\tmp"
rem les outils Android n'aiment pas les espaces dans les chemins : on construit via un raccourci (jonction) sans espace
if not exist C:\Android\tcshop_mobile mklink /J C:\Android\tcshop_mobile "%SRC:~0,-1%" >nul
cd /d C:\Android\tcshop_mobile
rem le cache de construction garde les chemins d'origine (avec espaces) : on le vide avant chaque APK
if exist .dart_tool\flutter_build rmdir /s /q .dart_tool\flutter_build
if exist build\app rmdir /s /q build\app
call "C:\Users\Ryan Beaufrere\Documents\DEV\flutter\bin\flutter.bat" build apk --release || exit /b 1
if not exist "%SRC%..\dist\mobile" mkdir "%SRC%..\dist\mobile"
copy /y build\app\outputs\flutter-apk\app-release.apk "%SRC%..\dist\mobile\TCShop-Mobile.apk"
echo Termine : dist\mobile\TCShop-Mobile.apk
