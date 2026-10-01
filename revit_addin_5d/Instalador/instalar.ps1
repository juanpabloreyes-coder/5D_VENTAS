$ErrorActionPreference = 'Stop'
$addinDir = Join-Path $env:AppData 'Autodesk\Revit\Addins\2025'
$nombreCarpeta = '03374_5D_VENTAS'                          # catalogo PPTO MAESTRO + resultados 5D (TEMPORAL_GCP_BIM)
$projectIdVentas = '5f587011-eb8e-4072-b4df-f16aee3915aa'   # proyecto VENTAS GCP en ACC

Write-Host ""
Write-Host " Buscando la carpeta 5D ($nombreCarpeta)..."
Write-Host " Esto puede tardar unos segundos, espera por favor."
Write-Host ""

$dcRoot = Join-Path $env:USERPROFILE 'DC'
$dir5d = $null
if (Test-Path $dcRoot) {
    $found = Get-ChildItem -Path $dcRoot -Recurse -Directory -Filter $nombreCarpeta -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { $dir5d = $found.FullName }
}

if (-not $dir5d) {
    Write-Host " No se encontro la carpeta `"$nombreCarpeta`" en este equipo."
    Write-Host ""
    Write-Host " Es posible que el proyecto TEMPORAL_GCP_BIM aun no este disponible"
    Write-Host " en tu Desktop Connector, o que no tengas acceso a el todavia."
    Write-Host ""
    Write-Host " Avisale a Juan Pablo con este mensaje para revisarlo juntos."
    Write-Host ""
    Read-Host " Presiona Enter para salir"
    exit 1
}

New-Item -ItemType Directory -Force -Path $addinDir | Out-Null
Copy-Item (Join-Path $PSScriptRoot 'Sync5D.dll') (Join-Path $addinDir 'Sync5D.dll') -Force
Copy-Item (Join-Path $PSScriptRoot 'Sync5D.addin') (Join-Path $addinDir 'Sync5D.addin') -Force

$cfg = [ordered]@{
    carpeta_5d = $dir5d
    project_id = $projectIdVentas
    ruta_catalogos = '02_PRESUPUESTOS\021_AUXILIARES\0212_CUANTIFICACIONES\02121_CATALOGOS'
    proyecto_acc = 'VENTAS GCP'
}
$json = $cfg | ConvertTo-Json
[System.IO.File]::WriteAllText((Join-Path $addinDir 'sync5d-config.json'), $json, (New-Object System.Text.UTF8Encoding($false)))

if (Test-Path (Join-Path $addinDir 'Sync5D.dll')) {
    Write-Host " Listo. Sync5D quedo instalado."
    Write-Host " Carpeta 5D (catalogo y resultados): $dir5d"
    Write-Host ""
    Write-Host " Siguiente paso: abre Revit normalmente."
    Write-Host " Si aparece un aviso de seguridad `"Unsigned Add-In`", elige `"Always Load`"."
    Write-Host " Veras la pestana `"5D`" con el boton `"Exportar Presupuesto`"."
}
else {
    Write-Host " Algo no se copio bien. Avisale a Juan Pablo con una captura de esta ventana."
}

Write-Host ""
Read-Host " Presiona Enter para cerrar"
