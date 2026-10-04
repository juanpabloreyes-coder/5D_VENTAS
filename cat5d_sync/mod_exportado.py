"""Modulo "Exportado vs Revit": auditoria del Excel de presupuesto (el consumible) contra Revit.

El Excel lo genera el boton "Exportar Presupuesto" del add-in Sync5D y queda en
<Proyecto>\\02_PRESUPUESTOS\\021_AUXILIARES\\0212_CUANTIFICACIONES\\02121_CATALOGOS. Al exportar, el add-in guarda:
  - en el Excel, la hoja oculta "_5D_META" (quien, cuando, modelo, id de exportacion);
  - en 03374_5D_VENTAS\\exportaciones\\<AAAA-MM>\\*.json, la FOTO de lo exportado (contenido de cada hoja y las
    tablas 5D tal como estaban en Revit).

Por modelo y mes se toma la ULTIMA exportacion del mes y se mide:
  - % Integridad = filas de Hoja1/Hoja2 del Excel en ACC iguales a la foto de exportacion.
    Lo distinto se le atribuye a quien subio versiones posteriores del Excel (historial de ACC).
  - % Vigencia   = filas de las tablas 5D exportadas iguales a las del Revit actual (foto de la ultima
    sincronizacion posterior a la exportacion). Si nadie sincronizo despues, esta vigente.
Responsable: el integrante con mas sincronizaciones del modelo en el mes (como todos los reportes);
tambien se muestra quien genero el Excel y quien lo modifico."""
import hashlib
import json
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from . import comun, validacion5d
from .checker_html import build_html
from .fuentes import cache_vigente, modelo_sin_ext, parse_fecha

log = logging.getLogger("cat5d_sync.exportado")

ID = "exportado"
NOMBRE = "Exportado vs Revit"
DESCRIPCION = ("Auditoría del Catálogo Exportado (02121_CATALOGOS) contra lo que se exportó de Revit (integridad) "
               "y contra el Revit actual (vigencia). Última exportación del mes.")
TARJETA = {"pct": {"num": "iguales", "den": "filas", "promedio": [["iguales", "filas"], ["vig_iguales", "vig_filas"]],
                   "etiqueta": "% general"},
           "cifras": [{"tipo": "pct", "num": "iguales", "den": "filas", "etiqueta": "integridad", "clase": "ok"},
                      {"tipo": "pct", "num": "vig_iguales", "den": "vig_filas", "etiqueta": "vigencia", "clase": "rev"},
                      {"campo": "modificadas", "etiqueta": "filas modif.", "clase": "mal"}]}
HOJAS_CONSUMIBLES = ("Hoja1", "Hoja2")


# ---------------------------------------------------------------- lectura
def leer_fotos(carpeta):
    """{export_id: foto} de 03374_5D_VENTAS\\exportaciones\\<AAAA-MM>\\*.json"""
    fotos, carpeta = {}, Path(carpeta)
    if not carpeta.exists():
        return fotos
    for f in carpeta.glob("*/*.json"):
        try:
            j = json.loads(f.read_text(encoding="utf-8-sig"))
            fotos[j["info"]["export_id"]] = j
        except Exception as e:
            log.warning("Foto de exportacion ilegible %s: %s", f.name, e)
    return fotos


def _carpetas_catalogos(aps, cfg):
    """[(proyecto, folder_id)] de 02121_CATALOGOS en cada proyecto de VENTAS (Data Management).
    Se guarda en cache (ver fuentes.cache_vigente) para no recorrer las carpetas en cada corrida."""
    a = cfg["aps"]
    pid = aps.con_b(a["project_id"])
    cache_p = Path(cfg.get("_cache_carpetas", "cache/carpetas_catalogos.json"))
    try:
        c = json.loads(cache_p.read_text(encoding="utf-8"))
        if cache_vigente(c["guardado"]):
            return pid, [tuple(x) for x in c["carpetas"]]
    except Exception:
        pass
    pid, salida = _carpetas_catalogos_acc(aps, cfg)
    try:
        cache_p.parent.mkdir(parents=True, exist_ok=True)
        cache_p.write_text(json.dumps({"guardado": datetime.now().isoformat(timespec="seconds"), "carpetas": salida},
                                      ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return pid, salida


def _carpetas_catalogos_acc(aps, cfg):
    a = cfg["aps"]
    hub, pid = aps.con_b(a["account_id"]), aps.con_b(a["project_id"])
    raices = [n.lower() for n in cfg.get("raiz_nombres", ["Project Files"])]
    raiz = next((t for t in aps.top_folders(hub, pid) if t["name"].strip().lower() in raices), None)
    if not raiz:
        return pid, []
    partes = [p for p in cfg.get("ruta_catalogos", "02_PRESUPUESTOS/021_AUXILIARES/0212_CUANTIFICACIONES/02121_CATALOGOS")
              .replace("\\", "/").split("/") if p]
    salida = []
    proyectos, _ = aps.contenido(pid, raiz["id"])
    for p in proyectos:
        if p["name"].strip().upper().startswith("Z_"):
            continue
        fid = p["id"]
        for parte in partes:
            carpetas, _ = aps.contenido(pid, fid)
            sig = next((c for c in carpetas if c["name"].strip().lower() == parte.lower()), None)
            if not sig:
                fid = None
                break
            fid = sig["id"]
        if fid:
            salida.append((p["name"].strip(), fid))
    return pid, salida


def leer_excels(aps, cfg, cache_dir):
    """Excels de presupuesto en ACC con su historial de versiones y su contenido actual.
    Las descargas se guardan en cache por version (cada version se baja una sola vez)."""
    pid, carpetas = _carpetas_catalogos(aps, cfg)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    excels = []
    for proyecto, fid in carpetas:
        _, items = aps.contenido(pid, fid)
        for it in items:
            if not it["name"].lower().endswith((".xlsx", ".xlsm")):
                continue
            versiones = sorted(aps.versiones(pid, it["item_id"]), key=lambda v: v.get("numero") or 0)
            if not versiones:
                continue
            ultima = versiones[-1]
            ruta = cache_dir / (hashlib.sha1(ultima["version_id"].encode()).hexdigest() + Path(it["name"]).suffix)
            if not ruta.exists():
                try:
                    ruta.write_bytes(aps.descargar_version(pid, ultima["version_id"]))
                except Exception as e:
                    log.warning("No se pudo descargar %s: %s", it["name"], e)
                    continue
            excels.append({"proyecto": proyecto, "archivo": it["name"], "item_id": it["item_id"],
                           "versiones": versiones, "local": str(ruta)})
    log.info("Excels de presupuesto en 02121_CATALOGOS: %d (en %d proyectos)", len(excels), len(carpetas))
    return excels


def leer_libro(ruta):
    """-> (meta: dict, contenido: {hoja: [filas normalizadas]}) ; meta vacio si no es del boton nuevo."""
    from openpyxl import load_workbook
    wb = load_workbook(ruta, data_only=True)
    meta = {}
    if "_5D_META" in wb.sheetnames:
        for fila in wb["_5D_META"].iter_rows(values_only=True):
            if fila and fila[0] == "HOJA":
                break
            if fila and fila[0]:
                meta[str(fila[0])] = "" if fila[1] is None else str(fila[1])
    contenido = {}
    for ws in wb.worksheets:
        if ws.title == "_5D_META":
            continue
        desde = 10 if ws.title in HOJAS_CONSUMIBLES else 1
        filas = [comun.norm_fila(f) for f in ws.iter_rows(min_row=desde, values_only=True)]
        while filas and not filas[-1]:
            filas.pop()
        contenido[ws.title] = filas
    return meta, contenido


# ---------------------------------------------------------------- comparaciones
def _comparar(ref, act):
    """Filas por posicion. -> (total, iguales, [(fila_idx, ref, act)])"""
    total = max(len(ref), len(act))
    difs = []
    for i in range(total):
        a = ref[i] if i < len(ref) else []
        b = act[i] if i < len(act) else []
        if a != b:
            difs.append((i, a, b))
    return total, total - len(difs), difs


def _col(k):
    n, s = k + 1, ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _celdas(a, b):
    """Celdas distintas entre dos filas -> [(columna, antes, despues)]"""
    out = []
    for k in range(max(len(a), len(b))):
        x = a[k] if k < len(a) else ""
        y = b[k] if k < len(b) else ""
        if x != y:
            out.append((_col(k), x, y))
    return out


def _ref(fila, desde=1):
    """Codigo y concepto de una fila (para ubicarla): columnas B y C del presupuesto."""
    partes = [x for x in fila[desde:desde + 2] if x]
    return " · ".join(partes)


def integridad(foto_contenido, contenido):
    """Hoja1/Hoja2 (consumibles) -> %; las demas pestanas se reportan aparte."""
    total = iguales = 0
    filas_dif, pestanas_dif, filas_cambiadas = [], [], 0
    for hoja, ref in foto_contenido.items():
        ref = [comun.norm_fila(f) for f in ref]
        act = contenido.get(hoja)
        if hoja in HOJAS_CONSUMIBLES:
            t, ig, difs = _comparar(ref, act or [])
            total += t
            iguales += ig
            filas_cambiadas += len(difs)
            for i, a, b in difs:
                for col, x, y in _celdas(a, b):
                    filas_dif.append([hoja, str(10 + i), col, _ref(a or b), x or "(vacío)", y or "(vacío)"])
        else:
            if act is None:
                pestanas_dif.append([hoja, "Pestaña eliminada del Catálogo Exportado", ""])
                continue
            _, _, difs = _comparar(ref, act)
            if difs:
                pestanas_dif.append([hoja, f"{len(difs)} fila(s) distinta(s)", ", ".join(str(1 + i) for i, _, _ in difs[:12])])
    for hoja in contenido:
        if hoja not in foto_contenido:
            pestanas_dif.append([hoja, "Pestaña agregada al Catálogo Exportado", ""])
    return total, iguales, filas_dif, pestanas_dif, filas_cambiadas


def vigencia(tablas_exportadas, tablas_actuales):
    ref = {t["nombre"]: [comun.norm_fila(f) for f in t["filas"]] for t in tablas_exportadas}
    act = {t["nombre"]: [comun.norm_fila(f) for f in t["filas"]] for t in tablas_actuales}
    total = iguales = 0
    difs = []
    for nombre in sorted(set(ref) | set(act)):
        if nombre not in act:
            total += len(ref[nombre])
            difs.append([nombre, "", "", "", "Tabla eliminada o renombrada en Revit", ""])
            continue
        if nombre not in ref:
            total += len(act[nombre])
            difs.append([nombre, "", "", "", "", "Tabla nueva en Revit (no está en el Catálogo Exportado)"])
            continue
        t, ig, d = _comparar(ref[nombre], act[nombre])
        total += t
        iguales += ig
        for i, a, b in d:
            for col, x, y in _celdas(a, b):
                difs.append([nombre, str(1 + i), col, _ref(a or b, 0), x or "(vacío)", y or "(vacío)"])
    return total, iguales, difs


# ---------------------------------------------------------------- modulo
def construir(grupos, catalogo, personas, cfg, tz, aps=None, excels=None, fotos=None):
    """-> (modelos, avisos)"""
    avisos = []
    if excels is None:
        excels = leer_excels(aps, cfg, Path(cfg.get("_cache_excels", "cache/excels")))
    fotos = fotos or {}

    # Exportaciones por modelo y mes (la ultima del mes)
    exportaciones = {}
    sin_huella = defaultdict(list)
    for ex in excels:
        try:
            meta, contenido = leer_libro(ex["local"])
        except Exception as e:
            avisos.append(f"No se pudo leer {ex['archivo']} ({ex['proyecto']}): {str(e)[:100]}")
            continue
        if not meta.get("export_id"):
            sin_huella[ex["proyecto"]].append(ex["archivo"])
            continue
        iid = meta.get("item_id") or comun.item_id_de(meta.get("model_urn"))
        fecha = parse_fecha(meta.get("fecha"), tz)
        if not iid or not fecha:
            continue
        clave = (fecha.strftime("%Y-%m"), iid)
        if clave not in exportaciones or fecha > exportaciones[clave]["fecha"]:
            exportaciones[clave] = {"fecha": fecha, "meta": meta, "contenido": contenido, "excel": ex}
    for proy, archivos in sin_huella.items():
        avisos.append(f"{proy}: {len(archivos)} Catálogo(s) Exportado(s) sin huella (generados con el botón anterior, no se pueden auditar): "
                      + ", ".join(sorted(archivos)[:5]))

    # Sincronizaciones por modelo (todas, para la vigencia) y por mes (para el responsable)
    regs_modelo = defaultdict(list)
    for (mes, iid), regs in grupos.items():
        regs_modelo[iid].extend(regs)

    modelos = []
    for (mes, iid), e in sorted(exportaciones.items()):
        cat = catalogo.get(iid)
        if not cat:
            avisos.append(f"Exportación de un modelo fuera de 011_WIP de VENTAS: {e['meta'].get('modelo')} ({mes}).")
            continue
        meta = e["meta"]
        foto = fotos.get(meta["export_id"])
        ref_contenido = foto["contenido"] if foto else None
        if ref_contenido is None:
            avisos.append(f"{cat['modelo']} ({mes}): falta la foto de la exportación {meta['export_id'][:8]} en "
                          "03374_5D_VENTAS\\exportaciones; no se puede medir la integridad.")
            continue

        # Responsable del mes; si nadie del listado sincronizo, quien genero el Excel
        participantes, resp = comun.participantes(grupos.get((mes, iid), []), personas)
        genero, eq_gen = personas.resolver(meta.get("revit_user") or "")
        if not resp and eq_gen != "SIN EQUIPO":
            resp = {"integrante": genero, "equipo": eq_gen}
        if not resp:
            avisos.append(f"{cat['modelo']} ({mes}): exportado y sincronizado solo por personas fuera del listado (no cuenta).")
            continue

        # Integridad + quien modifico (versiones posteriores a la primera en ACC)
        total, iguales, filas_dif, pestanas_dif, filas_cambiadas = integridad(ref_contenido, e["contenido"])
        versiones = e["excel"]["versiones"]
        # El Excel se versiona (mismo nombre por modelo): la version que subio el boton es la primera creada
        # despues de la exportacion; solo las que vienen DESPUES de esa son cambios hechos fuera de Revit.
        from datetime import timedelta
        idx_boton = None
        for i, v in enumerate(versiones):
            cv = parse_fecha(v.get("creado"), tz)
            if cv and cv >= e["fecha"] - timedelta(minutes=2):
                idx_boton = i
                break
        posteriores = versiones[idx_boton + 1:] if idx_boton is not None else [v for v in versiones if (v.get("numero") or 0) > 1]
        modificaron = []
        if (filas_dif or pestanas_dif) and posteriores:
            for v in posteriores:
                nombre, eq = personas.resolver(v.get("creado_por") or "")
                modificaron.append(nombre if eq != "SIN EQUIPO" else (v.get("creado_por") or "(desconocido)"))
        modificaron = sorted(set(modificaron))

        # Vigencia: foto de tablas de la ultima sincronizacion POSTERIOR a la exportacion
        posteriores_sync = [r for r in regs_modelo.get(iid, [])
                            if r.get("_ultima") and r["_ultima"] > e["fecha"] and (r.get("modulos") or {}).get("tablas")]
        if posteriores_sync and foto.get("tablas_5d") is not None:
            ult = max(posteriores_sync, key=lambda r: r["_ultima"])
            vt, vi, vdif = vigencia(foto["tablas_5d"], ult["modulos"]["tablas"].get("tablas") or [])
            vig_fecha = ult["_ultima"]
        else:
            filas_tab = sum(len(t["filas"]) for t in (foto.get("tablas_5d") or []))
            vt, vi, vdif, vig_fecha = filas_tab, filas_tab, [], None

        # Exportado vs Revit no se valida a mano: las diferencias se corrigen en Revit y se vuelve a exportar.
        iguales_raw, vi_raw = iguales, vi
        pct = int(round(100.0 * iguales / total)) if total else 100
        pct_v = int(round(100.0 * vi / vt)) if vt else 100
        modelos.append({
            **comun.base_modelo(mes, iid, cat),
            "responsable": resp["integrante"], "equipo": resp["equipo"],
            "participantes": comun.participantes_json(participantes),
            "syncs": sum(p["syncs"] for p in participantes),
            "genero": genero if eq_gen != "SIN EQUIPO" else (meta.get("revit_user") or ""),
            "modificaron": modificaron,
            "archivo": e["excel"]["archivo"], "frente": meta.get("frente", ""),
            "fecha": e["fecha"].isoformat(timespec="minutes"),
            "filas": total, "iguales": iguales, "modificadas": filas_cambiadas, "pestanas_modificadas": len(pestanas_dif),
            "percent": pct, "vig_filas": vt, "vig_iguales": vi, "pct_vigencia": pct_v,
            "vig_fecha": vig_fecha.isoformat(timespec="minutes") if vig_fecha else "",
            "results": _results(meta, e, versiones, total, iguales, filas_dif, pestanas_dif, modificaron,
                                vt, vi, vdif, vig_fecha, pct, pct_v),
            "val_meta": {"modo": "exp", "modelo": cat["modelo"], "item_id": iid,
                         "archivo": validacion5d.archivo("", iid).name,
                         "int": {"total": total, "raw": iguales_raw, "iguales": iguales},
                         "vig": {"total": vt, "raw": vi_raw, "iguales": vi},
                         "revisados": validacion5d.leer_revisados(cfg.get("_carpeta_5d"), iid)},
        })
    return modelos, avisos


def _results(meta, e, versiones, total, iguales, filas_dif, pestanas_dif, modificaron, vt, vi, vdif, vig_fecha, pct, pct_v,
             val_int=None, val_vig=None):
    r = []
    r.append({"section": "RESUMEN", "name": "Exportación", "status": "INFO", "score": False,
              "summary": f"{e['excel']['archivo']} · {e['fecha'].strftime('%d/%m/%Y %H:%M')} · generó "
                         f"{meta.get('revit_user') or '-'} · frente {meta.get('frente') or '-'}",
              "headers": [], "rows": []})
    r.append({"section": "RESUMEN", "name": "% INTEGRIDAD", "status": "PASS" if pct == 100 else "FAIL", "score": False,
              "summary": f"{pct}% · {iguales} de {total} filas de Hoja1/Hoja2 iguales a lo exportado desde Revit.",
              "headers": [], "rows": []})
    r.append({"section": "RESUMEN", "name": "% VIGENCIA", "status": "PASS" if pct_v == 100 else "FAIL", "score": False,
              "summary": (f"{pct_v}% · {vi} de {vt} filas de las tablas 5D siguen igual en Revit "
                          f"(sincronización del {vig_fecha.strftime('%d/%m/%Y %H:%M')})." if vig_fecha else
                          "Vigente: nadie ha sincronizado el modelo después de la exportación."),
              "headers": [], "rows": []})
    r.append({"section": "INTEGRIDAD", "name": "FILAS MODIFICADAS EN EL CATÁLOGO EXPORTADO", "status": "FAIL" if filas_dif else "PASS",
              "score": False,
              "summary": (f"{total - iguales} fila(s) de Hoja1/Hoja2 distintas a lo exportado ({len(filas_dif)} celda(s))"
                          + (f" · modificó: {', '.join(modificaron)}." if modificaron else ".")) if filas_dif
              else "Hoja1 y Hoja2 coinciden exactamente con lo exportado desde Revit.",
              "headers": ["Hoja", "Fila", "Columna", "Concepto", "Revit", "Exportado"], "rows": filas_dif,
              "resaltar": ["Columna"], "diff": ("Revit", "Exportado")})
    r.append({"section": "INTEGRIDAD", "name": "PESTAÑAS MODIFICADAS", "status": "FAIL" if pestanas_dif else "PASS",
              "score": False, "summary": f"Pestañas de tablas con cambios: {len(pestanas_dif)}" if pestanas_dif
              else "Las pestañas de las tablas no tienen cambios.",
              "headers": ["Pestaña", "Cambio", "Filas"], "rows": pestanas_dif, "resaltar": ["Cambio"]})
    r.append({"section": "INTEGRIDAD", "name": "VERSIONES DEL CATÁLOGO EXPORTADO EN ACC", "status": "INFO", "score": False,
              "summary": f"{len(versiones)} versión(es). Cada exportación del botón sube una versión; las que se suben después de la última exportación son cambios hechos fuera de Revit.",
              "headers": ["Versión", "Fecha", "Subió"],
              "rows": [[str(v.get("numero")), str(v.get("creado") or "")[:16].replace("T", " "), v.get("creado_por") or ""]
                       for v in versiones]})
    r.append({"section": "VIGENCIA", "name": "TABLAS CON CAMBIOS DESDE LA EXPORTACIÓN",
              "status": "FAIL" if vdif else "PASS", "score": False,
              "summary": f"{vt - vi} fila(s) cambiaron en Revit después de la exportación ({len(vdif)} celda(s)): hay que volver a exportar."
              if vdif else "Las tablas 5D de Revit siguen igual que en la exportación.",
              "headers": ["Tabla", "Fila", "Columna", "Concepto", "Exportado", "Revit"], "rows": vdif,
              "resaltar": ["Columna"], "diff": ("Exportado", "Revit")})
    for x in r:  # identidad y firma de cada recuadro (marca "Revisado")
        x["key"] = f"{x['section']}|{x['name']}"
        x["sig"] = validacion5d.firma(x["rows"] or x["summary"])
        if x.get("diff"):  # la comparacion (Revit vs Exportado, apilada) va antes del Concepto para verla sin desplazar
            h = x["headers"]
            orden = [h.index(c) for c in h if c != "Concepto"] + [h.index("Concepto")]
            x["headers"] = [h[i] for i in orden]
            x["rows"] = [[f[i] if i < len(f) else "" for i in orden] for f in x["rows"]]
    return r


def pagina(mes, proyecto, modelos, cfg):
    modelos = sorted(modelos, key=lambda m: m["modelo"])
    ultima = max((datetime.fromisoformat(m["fecha"]) for m in modelos if m["fecha"]), default=None)
    reports = [{
        "name": m["modelo"],
        "path": f"Responsable: {m['responsable']} · Generó: {m['genero'] or '-'}"
                + (f" · Modificó: {', '.join(m['modificaron'])}" if m["modificaron"] else ""),
        "kind": "HOST", "kind_label": m["disciplina"], "results": m["results"],
        "percent_fijo": int(round((m["percent"] + m["pct_vigencia"]) / 2)), "failed_fijo": m["modificadas"] + m["pestanas_modificadas"] + (1 if m["pct_vigencia"] < 100 else 0),
        "responsable": m["responsable"], "participantes": m["participantes"],
        "fecha_auditoria": datetime.fromisoformat(m["fecha"]).strftime("%d/%m/%Y %H:%M"),
        "val_meta": m.get("val_meta"),
    } for m in modelos]
    filas = sum(m["filas"] for m in modelos)
    iguales = sum(m["iguales"] for m in modelos)
    vt = sum(m["vig_filas"] for m in modelos)
    vi = sum(m["vig_iguales"] for m in modelos)
    pct = int(round(100.0 * iguales / filas)) if filas else 100
    pct_v = int(round(100.0 * vi / vt)) if vt else 100
    pct_g = int(round((100.0 * iguales / filas if filas else 100) / 2 + (100.0 * vi / vt if vt else 100) / 2))
    raiz = (cfg.get("raiz_nombres") or ["Project Files"])[0]
    ruta = f"{cfg.get('proyecto_acc', 'VENTAS GCP')} / {raiz} / {proyecto} / 02121_CATALOGOS · {mes}"
    resumen = {
        "titulo": "Exportado vs Revit.", "subtitulo": "Integridad del presupuesto.",
        "copy": "Comprueba que el Catálogo Exportado refleje exactamente lo que hay en Revit: que nadie lo haya "
                "modificado después de exportarlo (integridad) y que el modelo no haya cambiado desde entonces (vigencia).",
        "percent": pct_g, "score_label": "% GENERAL",
        "score_class": "score-red" if pct_g <= 70 else "score-orange" if pct_g < 100 else "score-green",
        "caption": f"Promedio de integridad {pct}% y vigencia {pct_v}%",
        "metricas": [("Modelos exportados", len(modelos), "total"), ("% Integridad", f"{pct}%", "pass" if pct == 100 else "fail"),
                     ("% Vigencia", f"{pct_v}%", "pass" if pct_v == 100 else "fail"),
                     ("Filas modificadas", sum(m["modificadas"] for m in modelos), "fail")],
    }
    return build_html(proyecto, ruta, comun.fecha_larga(ultima), reports, resumen=resumen,
                      extra_css=validacion5d.ESTILO, extra_script=validacion5d.SCRIPT,
                      footer_note=f"Exportado vs Revit · última exportación del mes · {comun.fecha_larga(ultima)}")
