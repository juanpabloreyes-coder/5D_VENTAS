"""Reporte 5D_VENTAS por MODULOS (una pestana por metrica 5D en el indice).

Modulos actuales:
  - base_datos : Base de Datos vs Revit   (mod_base_datos.py)
  - exportado  : Exportado vs Revit       (mod_exportado.py)
Para agregar una metrica nueva: un archivo mod_<id>.py con ID, NOMBRE, DESCRIPCION, TARJETA, construir() y
pagina(), y agregarlo a MODULOS en __main__.py. El indice y las paginas por proyecto se arman solos.

Salida:
  - Dashboard\\5D-Ventas-Report.html                      indice (pestanas por modulo, tarjetas por proyecto, filtros)
  - Dashboard\\5d\\<modulo>\\<AAAA-MM>\\<proyecto>.html     reporte del proyecto (diseno del Checker)
  - Data\\5D_VENTAS.json
"""
import json
import logging
from collections import defaultdict
from datetime import datetime

from . import comun

log = logging.getLogger("cat5d_sync.reporte")
FUENTE = "Sync5D (Revit) + APS Data Management"
MARCADOR = '<script id="cat5d-data" type="application/json"></script>'


def escribir(resultados, avisos, cfg, ruta, roster):
    """resultados: [(modulo, modelos)]"""
    html_index = ruta(cfg.get("html", "Dashboard/5D-Ventas-Report.html"))
    carpeta = html_index.parent / cfg.get("carpeta_proyectos", "5d")
    plantilla = ruta(cfg.get("plantilla", "Dashboard/5D-Ventas-Report.template.html"))
    json_path = ruta(cfg.get("json", "Data/5D_VENTAS.json"))

    modulos, resumen = [], []
    for mod, modelos in resultados:
        paginas, por_pagina = {}, defaultdict(list)
        for m in modelos:
            por_pagina[(m["mes"], m["proyecto"])].append(m)
        for (mes, proyecto), lst in por_pagina.items():
            html = mod.pagina(mes, proyecto, lst, cfg)
            rel = f"{mod.ID}/{mes}/{comun.slug(proyecto)}.html"
            comun.escribir_atomico(carpeta / rel, html, si_cambia=True)
            paginas[f"{mes}/{comun.slug(proyecto)}"] = {"href": f"{carpeta.name}/{rel}", "peso": len(html.encode("utf-8"))}
        filas = [{k: v for k, v in m.items() if k not in ("results", "item_id", "val_meta")}
                 for m in modelos]
        modulos.append({"id": mod.ID, "nombre": mod.NOMBRE, "descripcion": mod.DESCRIPCION, "tarjeta": mod.TARJETA,
                        "paginas": paginas, "rows": filas})
        resumen.append(f"{mod.NOMBRE}: {len(modelos)} modelo-mes en {len(paginas)} reportes de proyecto")

    datos = {"proyectoAcc": cfg.get("proyecto_acc", "VENTAS GCP"), "roster": roster, "avisos": avisos,
             "source": FUENTE, "modulos": modulos}
    # Sin cambios en los datos: no se reescribe (evita versiones nuevas en ACC)
    try:
        prev = json.loads(json_path.read_text(encoding="utf-8"))
        cambio_plantilla = html_index.exists() and plantilla.stat().st_mtime > html_index.stat().st_mtime
        if {k: v for k, v in prev.items() if k != "generadoEn"} == datos and html_index.exists() and not cambio_plantilla:
            return "SIN CAMBIOS: " + " · ".join(resumen) + ". Se conservan el JSON y el HTML existentes."
    except Exception:
        pass
    datos = {"generadoEn": datetime.now().astimezone().isoformat(timespec="minutes"), **datos}
    txt = json.dumps(datos, ensure_ascii=False, indent=1)
    template = plantilla.read_text(encoding="utf-8")
    if MARCADOR not in template:
        raise ValueError(f"La plantilla no tiene el marcador {MARCADOR}")
    index = template.replace(MARCADOR, '<script id="cat5d-data" type="application/json">' + txt.replace("</", "<\\/") + "</script>")
    comun.escribir_atomico(json_path, txt)
    comun.escribir_atomico(html_index, index)
    return "EXPORTACION COMPLETADA: " + " · ".join(resumen) + "."
