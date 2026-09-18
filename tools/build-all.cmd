@echo off
REM Run the full asset pipeline in order: reference views, action sheets,
REM then frame extraction, encoding and previews. Meant for a developer
REM checkout; the published package already contains the built assets.
setlocal
cd /d "%~dp0.."

echo === stage 1/2: reference views + action sheets (image model calls) ===
python tools\gen_art.py sheet || exit /b 1
python tools\gen_art.py actions || exit /b 1

echo.
echo === stage 2/2: frames, webm encoding, previews (local, no network) ===
python tools\build_assets.py all || exit /b 1

echo.
echo === package check ===
node tools\check-package.mjs || exit /b 1

echo.
echo Done. Assets are in assets\anims and assets\voice.
