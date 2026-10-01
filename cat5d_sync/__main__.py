"""5D_VENTAS: conceptos de Revit contra la Base de Datos de Presupuestos, sin boton y sin APIs de pago.

Uso (desde la carpeta 5D_VENTAS):
  python -m cat5d_sync run          # genera Dashboard\\5D-Ventas-Report.html (+ un HTML por proyecto y mes)
  python -m cat5d_sync diagnostico  # igual, pero NO escribe nada: imprime conteos y avisos

Los datos los escribe el add-in Sync5D de Revit (al sincronizar y al exportar el presupuesto) en carpeta_5d.
Credenciales APS: las mismas de PLANOS/PUBLICACIONES (APS_CLIENT_ID / APS_CLIENT_SECRET), solo para
leer el catalogo de modelos (Data Management, sin costo).
"""
import argparse
import json
import logging
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import comun, mod_base_datos, mod_exportado
from .aps import APS
from .fuentes import Personas, catalogo_modelos, leer_equipos
from .reporte import escribir

# Modulos del reporte 5D (una pestana cada uno). Para una metrica nueva: agregar aqui su mod_<id>.py.
MODULOS = [mod_base_datos, mod_exportado]

RAIZ = Path(__file__).resolve().parent.parent


def _ruta(v):
    p = Path(v)
    return p if p.is_absolute() else RAIZ / p


def _log_automation(msg):
    try:
        (RAIZ / "Automation").mkdir(exist_ok=True)
        with open(RAIZ / "Automation" / "cat5d_sync.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  CAT5DSYNC  {msg}\n")
    except Exception:
        pass


def _escribir_mapa(carpeta_5d, catalogo):
    """_modelos_ventas.json en la carpeta compartida: el boton "Exportar Presupuesto" lo usa para saber en que
    proyecto (y en que 02121_CATALOGOS) guardar el Excel de cada modelo. Solo se reescribe si cambio."""
    try:
        mapa = {"modelos": {iid: {"proyecto": c["proyecto"], "modelo": c["modelo"], "ruta": c.get("ruta", "")}
                            for iid, c in sorted(catalogo.items())}}
        txt = json.dumps(mapa, ensure_ascii=False, indent=1)
        if comun.escribir_atomico(Path(carpeta_5d) / "_modelos_ventas.json", txt, si_cambia=True):
            print("Mapa de modelos actualizado para el boton Exportar Presupuesto.")
    except Exception as e:
        print("AVISO: no se pudo escribir _modelos_ventas.json:", e)


def procesar(cfg, escribir_salida=True):
    tz = timezone(timedelta(hours=cfg.get("zona_horaria_utc", -6)))
    avisos = []

    cid, sec = os.environ.get("APS_CLIENT_ID"), os.environ.get("APS_CLIENT_SECRET")
    if not cid or not sec:
        raise SystemExit("Falta APS_CLIENT_ID / APS_CLIENT_SECRET (las mismas variables que usan los otros reportes).")
    aps = APS(cid, sec)
    catalogo, av = catalogo_modelos(aps, cfg, _ruta(cfg.get("cache", "cache/modelos_acc.json")))
    avisos += av
    carpeta_5d = _ruta(cfg["carpeta_5d"])
    if escribir_salida:
        _escribir_mapa(carpeta_5d, catalogo)

    grupos = comun.leer_registros(carpeta_5d / "resultados", tz, cfg["aps"]["project_id"])

    xlsx = _ruta(cfg["equipos_xlsx"])
    roster = []
    if xlsx.exists():
        equipos = leer_equipos(xlsx, cfg.get("equipos_hoja", "Integrantes"))
        # Solo para probar el reporte: integrantes extra que cuentan aunque no esten en el Excel de equipos.
        # Dejar la lista vacia en config.json al terminar las pruebas.
        from .fuentes import persona_compacta
        ya = {e["compacta"] for e in equipos}
        for extra in cfg.get("integrantes_prueba") or []:
            k = persona_compacta(extra.get("integrante", ""))
            if k and k not in ya:
                equipos.append({"integrante": extra["integrante"], "equipo": extra.get("equipo", "PRUEBAS"), "compacta": k})
                avisos.append(f"Modo prueba: {extra['integrante']} cuenta como integrante (config.json > integrantes_prueba).")
        personas = Personas(equipos, cfg.get("alias_personas"))
        por_equipo = {}
        for e in equipos:
            por_equipo.setdefault(e["equipo"], []).append(e["integrante"])
        roster = [{"equipo": k, "integrantes": v} for k, v in por_equipo.items()]
    else:
        avisos.append(f"No se encontro el Excel de equipos: {xlsx}. Nadie cuenta como integrante.")
        personas = Personas([], cfg.get("alias_personas"))

    resultados = []
    for mod in MODULOS:
        try:
            if mod is mod_exportado:
                excels = mod_exportado.leer_excels(aps, cfg, _ruta(cfg.get("cache_excels", "cache/excels")))
                fotos = mod_exportado.leer_fotos(carpeta_5d / "exportaciones")
                modelos, av = mod.construir(grupos, catalogo, personas, cfg, tz, excels=excels, fotos=fotos)
            else:
                modelos, av = mod.construir(grupos, catalogo, personas, cfg, tz)
        except Exception as e:
            log_err = f"Modulo {mod.NOMBRE}: {e}"
            avisos.append(log_err + " (el modulo quedo vacio en esta corrida)")
            modelos, av = [], []
        avisos += av
        resultados.append((mod, modelos))
        print(f"{mod.NOMBRE}: {len(modelos)} modelo-mes", dict(sorted(Counter(m['mes'] for m in modelos).items())))

    print(f"Modelos .rvt en VENTAS (011_WIP): {len(catalogo)}  |  modelo-mes sincronizados: {len(grupos)}")
    durs = [m["duracion_s"] for _, ms in resultados for m in ms if m.get("duracion_s") is not None]
    if durs:
        print(f"Tiempo de Base de Datos vs Revit en Revit: promedio {sum(durs)/len(durs):.1f} s, maximo {max(durs):.1f} s")
    if personas.no_resueltos:
        print("Personas fuera del listado (no cuentan):", ", ".join(sorted(personas.no_resueltos)))
    for a in avisos:
        print("AVISO:", a)

    if not escribir_salida:
        return "DIAGNOSTICO: no se escribio ningun archivo."
    return escribir(resultados, avisos, cfg, _ruta, roster)


def main():
    ap = argparse.ArgumentParser(prog="cat5d_sync")
    ap.add_argument("cmd", choices=["run", "diagnostico"])
    ap.add_argument("--config", default=str(RAIZ / "config.json"))
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))
    try:
        estado = procesar(cfg, escribir_salida=(a.cmd == "run"))
    except SystemExit:
        raise
    except Exception as e:
        _log_automation(f"ERROR: {e}. Se conservan los HTML anteriores.")
        print(f"\nERROR: {e}\nSe conservan los HTML anteriores.", file=sys.stderr)
        sys.exit(2)
    print("\n" + estado)
    if a.cmd == "run":
        _log_automation(estado)


if __name__ == "__main__":
    main()
