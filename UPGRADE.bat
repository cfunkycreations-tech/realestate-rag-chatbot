@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0upgrade.ps1"
echo.
echo Done. Open http://localhost:3000 and press Ctrl+Shift+R.
pause
