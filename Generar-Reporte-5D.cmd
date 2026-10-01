@echo off
REM Genera el indice de 5D_VENTAS y un HTML por proyecto y mes desde las revisiones 5D del add-in AuditSync.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
python -m cat5d_sync run
if errorlevel 1 pause
start "" "Dashboard\5D-Ventas-Report.html"
