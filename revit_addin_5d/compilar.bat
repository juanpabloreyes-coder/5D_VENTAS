@echo off
REM Compila Sync5D.dll (Release) y la copia a la carpeta Instalador.
cd /d "%~dp0"
dotnet build Sync5D.csproj -c Release
if errorlevel 1 (
  echo.
  echo ERROR: no compilo. No se copio nada.
  pause
  exit /b 1
)
copy /Y "bin\Release\net8.0-windows\Sync5D.dll" "Instalador\Sync5D.dll"
echo.
echo Listo: Instalador\Sync5D.dll actualizado.
pause
