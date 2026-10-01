@echo off
title Quitar Sync5D (5D_VENTAS)

set "ADDIN_DIR=%AppData%\Autodesk\Revit\Addins\2025"

echo.
echo  Quitando Sync5D...
echo.

del /F /Q "%ADDIN_DIR%\Sync5D.dll" 2>nul
del /F /Q "%ADDIN_DIR%\Sync5D.addin" 2>nul
del /F /Q "%ADDIN_DIR%\sync5d-config.json" 2>nul
del /F /Q "%ADDIN_DIR%\Sync5D.pdb" 2>nul

echo  Listo, Sync5D ya no se cargara la proxima vez que abras Revit.
echo.
pause
