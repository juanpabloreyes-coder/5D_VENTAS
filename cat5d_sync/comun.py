"""Piezas comunes de los modulos del reporte 5D: lectura de lo que guarda el add-in Sync5D al sincronizar,
responsable del mes (misma regla en todos los reportes de VENTAS) y escritura de archivos."""
import json
import logging
import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from .fuentes import disciplina, parse_fecha

log = logging.getLogger("cat5d_sync.comun")
PREFIJO_LINAJE = "urn:adsk.wipprod:dm.lineage:"
MES_RE = re.compile(r"^\d{4}-\d{2}$")


def slug(texto):
    s = unicodedata.normalize("NFD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "proyecto"


def item_id_de(urn, archivo=None):
    urn = str(urn or "")
    i = urn.lower().find("dm.lineage:")
    if i >= 0:
        return PREFIJO_LINAJE + urn[i + len("dm.lineage:"):].split("?")[0]
    if archivo is not None:
        m = re.match(r"^urn_(.+?)__", Path(archivo).name)
        return PREFIJO_LINAJE + m.group(1) if m else None
    return None


def leer_registros(carpeta, tz, project_id=None):
    """Archivos del add-in al sincronizar: <carpeta>\\<AAAA-MM>\\urn_<linaje>__<PC>_<usuario>.json
    -> {(mes, item_id): [registro, ...]}  (un registro por persona/maquina)"""
    carpeta = Path(carpeta)
    propio = str(project_id or "").lower().removeprefix("b.")
    grupos, otros, malos = defaultdict(list), 0, 0
    if not carpeta.exists():
        log.warning("No existe la carpeta de resultados 5D: %s", carpeta)
        return grupos
    for dmes in sorted(p for p in carpeta.iterdir() if p.is_dir() and MES_RE.match(p.name)):
        for f in sorted(dmes.glob("urn_*.json")):
            try:
                reg = json.loads(f.read_text(encoding="utf-8-sig"))
            except Exception as e:
                malos += 1
                log.warning("No se pudo leer %s: %s", f.name, e)
                continue
            pid = str(reg.get("project_id") or "").lower().removeprefix("b.")
            if propio and pid and pid != propio:
                otros += 1
                continue
            iid = item_id_de(reg.get("model_urn"), f)
            if not iid:
                continue
            reg["_ultima"] = parse_fecha(reg.get("ultima_sync"), tz)
            reg.setdefault("modulos", {})
            # Formato anterior (la revision 5D vivia dentro de AuditSync)
            if reg.get("catalogo5d") and "base_datos" not in reg["modulos"]:
                reg["modulos"]["base_datos"] = reg["catalogo5d"]
            grupos[(dmes.name, iid)].append(reg)
    log.info("Sincronizaciones 5D: %d modelo-mes (%d archivos de otros proyectos, %d ilegibles)", len(grupos), otros, malos)
    return grupos


def participantes(regs, personas):
    """Integrantes del listado que sincronizaron el modelo (varias maquinas = una persona).
    -> (lista ordenada, responsable) ; responsable = mas sincronizaciones (empate: el ultimo)."""
    part = {}
    for r in regs:
        integrante, equipo = personas.resolver(r.get("revit_user") or "")
        if equipo == "SIN EQUIPO":
            continue
        p = part.setdefault(integrante, {"integrante": integrante, "equipo": equipo, "syncs": 0, "_ultima": None})
        p["syncs"] += int(r.get("syncs") or 0)
        if r.get("_ultima") and (p["_ultima"] is None or r["_ultima"] > p["_ultima"]):
            p["_ultima"] = r["_ultima"]
    if not part:
        return [], None
    resp = max(part.values(), key=lambda p: (p["syncs"], p["_ultima"] or datetime.min))
    lista = sorted(part.values(), key=lambda p: (-p["syncs"], p["integrante"]))
    return lista, resp


def participantes_json(lista):
    return [{"integrante": p["integrante"], "equipo": p["equipo"], "syncs": p["syncs"],
             "ultima": p["_ultima"].strftime("%d/%m/%Y %H:%M") if p.get("_ultima") else ""} for p in lista]


def base_modelo(mes, iid, cat):
    return {"mes": mes, "item_id": iid, "proyecto": cat["proyecto"], "slug": slug(cat["proyecto"]),
            "modelo": cat["modelo"], "ruta": cat.get("ruta", ""), "disciplina": disciplina(cat["modelo"])}


def fecha_larga(dt):
    return dt.strftime("%d/%m/%Y %I:%M:%S %p") if dt else ""


def escribir_atomico(destino, contenido, si_cambia=False):
    destino = Path(destino)
    if si_cambia and destino.exists() and destino.read_text(encoding="utf-8") == contenido:
        return False
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(destino.suffix + ".tmp")
    tmp.write_text(contenido, encoding="utf-8")
    tmp.replace(destino)
    return True


def norm(v):
    """Valor de celda comparable: numeros con el mismo formato ('52.50' = 52.5), texto sin espacios extra."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        f = float(v)
        return str(int(f)) if f.is_integer() else repr(f)
    s = str(v).strip()
    if re.fullmatch(r"-?\d+(\.\d+)?", s):
        f = float(s)
        return str(int(f)) if f.is_integer() else repr(f)
    return s


def norm_fila(fila):
    f = [norm(v) for v in (fila or [])]
    while f and f[-1] == "":
        f.pop()
    return f
