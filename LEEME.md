# 5D_VENTAS · Métricas 5D (sin botón de auditoría, sin Power BI, sin APIs de pago)

Reporte de métricas 5D del proyecto **VENTAS GCP**, con una **pestaña por módulo** (preparado para agregar más):

| Módulo | Qué mide | De dónde sale |
|---|---|---|
| **Base de Datos vs Revit** | Conceptos de Revit contra la Base de Datos de Presupuestos (código, control, descripción, unidad, partida) | Add-in **Sync5D** al sincronizar (vista 3D "ACC", catálogo PPTO MAESTRO de `03374_5D_VENTAS`) |
| **Exportado vs Revit** | Que el Excel de presupuesto (el consumible) refleje exactamente Revit: **% integridad** y **% vigencia** | Botón **Exportar Presupuesto** (pestaña 5D de Revit) + Excel en `02121_CATALOGOS` + historial de ACC |

## Add-in Sync5D (`revit_addin_5d/`, 4º add-in, independiente)
- **Pestaña "5D" → "Exportar Presupuesto"**: hace lo mismo que el botón de GCP_PLUGIN (una pestaña por tabla, plantilla
  "PRESUPUESTO DE OBRA") y además:
  - deja **Hoja1 y Hoja2 compiladas** igual que las macros "Generar Presupuesto" y "Extraer conceptos base", pero
    solo con pestañas 000–999; el Excel sale **.xlsx sin macros ni botones**;
  - pide solo el **frente de trabajo** (opciones de la tabla FRENTES del modelo);
  - agrega la hoja oculta **_5D_META** (quién, cuándo, modelo, id de exportación);
  - guarda una **foto de la exportación** en `03374_5D_VENTAS\exportaciones\<AAAA-MM>\`;
  - guarda el Excel en `<Proyecto>\02_PRESUPUESTOS\021_AUXILIARES\0212_CUANTIFICACIONES\02121_CATALOGOS\<Modelo>_<fecha>.xlsx`
    (el proyecto sale de `_modelos_ventas.json`, que escribe este reporte) y lo abre.
- **Al sincronizar** un modelo de VENTAS corre los módulos (`App.cs` → `Modulos`): `base_datos` y `tablas` (foto de las
  tablas 5D para la vigencia). Resultado en `03374_5D_VENTAS\resultados\<AAAA-MM>\urn_<modelo>__<PC>_<usuario>.json`.
- Compilar: `revit_addin_5d\compilar.bat`. Instalar: `revit_addin_5d\Instalador\instalar.bat`.
- **Pendiente:** retirar el botón "Exportar Presupuesto" de GCP_PLUGIN cuando todos usen el nuevo.

## Reglas
- **Responsable** (todos los módulos): integrante del Excel con más sincronizaciones del modelo en el mes (empate: el
  último). Quien no está en el Excel no aparece ni cuenta.
- **Base de Datos vs Revit**: revisión de la última sincronización del mes. % OK = OK / (OK + Errores + Review);
  los códigos 1111111111 son Review.
- **Exportado vs Revit**: última exportación del mes de cada modelo.
  - **% Integridad** = filas de Hoja1/Hoja2 del Excel en ACC iguales a la foto de exportación. Lo distinto se le
    atribuye a quien subió versiones posteriores del Excel (**Modificó**, historial de ACC).
  - **% Vigencia** = filas de las tablas 5D exportadas iguales a las del Revit actual (última sincronización
    posterior a la exportación). Si nadie sincronizó después, está vigente.
  - Se muestran también **Generó** (quien exportó) y las pestañas de tablas modificadas.
  - Excel sin `_5D_META` (botón anterior): aviso "sin huella", no se pueden auditar.

## Uso
```
python -m cat5d_sync run           # índice + reportes por proyecto de cada módulo
python -m cat5d_sync diagnostico   # no escribe nada: conteos y avisos
```
O doble clic en `Generar-Reporte-5D.cmd`. Automático: `programar_tarea.bat` (tarea **Catalogo5DSync_VENTAS_Mensual**,
23:55, cierre del último día del mes).

## Agregar una métrica 5D nueva
1. Add-in: una entrada más en `Modulos` (`App.cs`) con su id y la función que la calcula al sincronizar.
2. Reporte: `cat5d_sync\mod_<id>.py` con `ID`, `NOMBRE`, `DESCRIPCION`, `TARJETA`, `construir()` y `pagina()`, y
   agregarlo a `MODULOS` en `__main__.py`. Aparece sola como pestaña nueva.

## Costo
$0: todo corre en Revit o con Data Management de APS (catálogo de modelos, Excels y su historial).
