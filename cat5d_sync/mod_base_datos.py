"""Modulo "Base de Datos vs Revit": conceptos de Revit contra la Base de Datos de Presupuestos.
Corre en Revit al sincronizar (add-in Sync5D, Catalogo5D.cs) con el catalogo PPTO MAESTRO de 03374_5D_VENTAS
y la vista 3D "ACC" del modelo; aqui se toma, por modelo y mes, la revision de la ULTIMA sincronizacion.
% OK = OK / (OK + Errores + Review), igual que el boton. Los codigos 1111111111 cuentan como Review."""
from collections import Counter
from pathlib import Path
from datetime import datetime

from . import catalogo_bd, comun, validacion5d
from .checker_html import build_html
from .fuentes import modelo_sin_ext, parse_fecha

ID = "base_datos"
NOMBRE = "Base de Datos vs Revit"
DESCRIPCION = ("Conceptos de Revit contra la Base de Datos de Presupuestos (código, control, descripción, unidad y "
               "partida). Revisión de la última sincronización del mes, vista 3D ACC.")
# Tarjeta del indice: % principal y tres cifras (sumas de campos de cada modelo)
TARJETA = {"pct": {"num": "ok", "den": "evaluados", "etiqueta": "% OK"},
           "cifras": [{"campo": "ok", "etiqueta": "ok", "clase": "ok"},
                      {"campo": "review", "etiqueta": "review", "clase": "rev"},
                      {"campo": "error", "etiqueta": "errores", "clase": "mal"}]}


COLUMNAS = ["ID", "Categoría", "Tipo", "Concepto", "Control", "Código", "Descripción", "Unidad", "Partida revisada"]
SECCIONES = [("BASE", "CONCEPTO BASE"), ("AC", "AC"), ("REC", "REC"), ("ADD", "ADD")]
REVIEW_CARD = "REVISIÓN MANUAL (CÓDIGO 1111111111)"
MANUAL_ERR = "MARCADOS MANUALMENTE COMO ERROR"


def _tabla(filas, con_motivo=False, con_blancos=False):
    out = []
    for f in filas:
        fila = [f[0], f[1], f[2], f[4], f[5], f[6], f[7], f[8], f[9]]
        if con_motivo:
            fila.append(f[11])
        if con_blancos:
            fila.append(f[12])
        out.append(fila)
    return out


def resaltar(motivo):
    """Columnas que explican el motivo del recuadro (se resaltan en la tabla)."""
    m = (motivo or "").lower()
    cols = []
    if "tipo no existe" in m:
        cols.append("Tipo")
    if "código no pertenece" in m:
        cols += ["Tipo", "Código"]
    if "código vacío" in m or "código especial" in m or "1111111111" in m:
        cols.append("Código")
    if "control" in m:
        cols.append("Control")
    if "descripción" in m:
        cols.append("Descripción")
    if "unidad" in m:
        cols.append("Unidad")
    if "partida" in m:
        cols.append("Partida revisada")
    if "datos no coinciden" in m:
        cols += ["Control", "Descripción", "Unidad", "Partida revisada"]
    return list(dict.fromkeys(cols))


CMP_COLS = {"Control": 5, "Código": 6, "Descripción": 7, "Unidad": 8, "Partida revisada": 9}  # columna -> indice en la fila del add-in
_POS_TABLA = {"Control": 4, "Código": 5, "Descripción": 6, "Unidad": 7, "Partida revisada": 8}  # columna -> indice en la tabla


def comparacion(f, catalogos):
    """Lo que espera el catalogo en los campos que NO coinciden -> {indice_en_tabla: {"v": valor, "diff": bool}}"""
    if f[10] == "OK":
        return None
    esp = catalogo_bd.esperado(f, catalogos)
    if not esp:
        return None
    out = {}
    if "codigos" in esp:
        lista = esp["codigos"]
        out[_POS_TABLA["Código"]] = {"v": "Códigos del tipo en catálogo: " + (", ".join(lista[:30]) + (" …" if len(lista) > 30 else "")),
                                     "diff": False}
        return out
    k = catalogo_bd.k
    if catalogo_bd.control(f[5]).upper() != esp["control"].upper():
        out[_POS_TABLA["Control"]] = {"v": esp["control"] or "(vacío)", "diff": True}
    if k(f[7]) != k(esp["descripcion"]):
        out[_POS_TABLA["Descripción"]] = {"v": esp["descripcion"] or "(vacío)", "diff": True}
    if k(f[8]) != k(esp["unidad"]):
        out[_POS_TABLA["Unidad"]] = {"v": esp["unidad"] or "(vacío)", "diff": True}
    if esp["partida"] and k(f[9]) != k(esp["partida"]):
        out[_POS_TABLA["Partida revisada"]] = {"v": esp["partida"], "diff": True}
    return out or None


def a_results(rev, max_ok, vals=None, catalogos=None):
    """Convierte la revision 5D del add-in en tarjetas con la forma del Checker:
    una seccion por alcance (Base / AC / REC / ADD) con una tarjeta de coincidencias, una por cada
    motivo de error y una de revision manual; y una seccion de captura de parametros."""
    filas = rev.get("filas") or []
    vals = vals or [None] * len(filas)
    vpor = {id(f): v for f, v in zip(filas, vals)}  # controles de validacion por fila
    t = rev.get("totales") or {}
    results = []
    capt, blanc = int(t.get("parametros_capturados", 0)), int(t.get("parametros_en_blanco", 0))
    pct_par = round(100.0 * capt / (capt + blanc)) if capt + blanc else 0
    results.append({"section": "RESUMEN", "name": "Vista y catálogo revisados", "status": "INFO", "score": False,
                    "summary": f"Vista: {rev.get('vista') or '(sin vista ACC)'} · Catálogo: {rev.get('catalogo') or '-'}",
                    "headers": [], "rows": []})
    results.append({"section": "RESUMEN", "name": "Elementos del modelo", "status": "INFO", "score": False,
                    "summary": f"{t.get('modelo', 0)} elementos en la vista · {t.get('revisados', 0)} revisados · "
                               f"{t.get('ignorados', 0)} ignorados · {t.get('conceptos_base', 0)} conceptos base · "
                               f"{t.get('conceptos_add', 0)} conceptos ADD/AC/REC", "headers": [], "rows": []})
    if rev.get("aviso"):
        results.append({"section": "RESUMEN", "name": "VISTA 3D ACC", "status": "FAIL", "score": False,
                        "summary": rev["aviso"], "headers": [], "rows": []})
    for clave, titulo in SECCIONES:
        del_alcance = [f for f in filas if f[3] == clave]
        if not del_alcance:
            continue
        # Cada concepto va al recuadro de su estatus ACTUAL (con validaciones):
        #   OK -> Coinciden ; Review -> Revision manual ; Error -> su motivo de origen, o
        #   "Marcados manualmente como Error" si de origen no era error.
        ok, review, manual, motivos = [], [], [], {}
        for f in del_alcance:
            v = vpor.get(id(f))
            if v is not None:
                v["sec"] = titulo
                v["home"] = f"{titulo}|{v['m0'].upper()}" if v["o"] == "ERROR" else f"{titulo}|{MANUAL_ERR}"
                if v["o"] == "ERROR":
                    motivos.setdefault(v["m0"], [])
            e = f[10]
            if e == "OK":
                ok.append(f)
            elif e == "REVIEW":
                review.append(f)
            elif v is not None and v["o"] != "ERROR":
                manual.append(f)
            else:
                motivos.setdefault(v["m0"] if v else f[11], []).append(f)
        hay_val = any(vpor.get(id(f)) for f in del_alcance)
        errores = [f for lst in motivos.values() for f in lst] + manual
        resumen_ok = f"{len(ok)} de {len(del_alcance)} conceptos coinciden con el catálogo."
        ok = sorted(ok, key=lambda f: vpor.get(id(f)) is None)  # los validables primero (no se recortan)
        if len(ok) > max_ok:
            resumen_ok += f" (se muestran los primeros {max_ok})"
            ok = ok[:max_ok]
        if ok or hay_val:
            results.append({"section": titulo, "name": "COINCIDEN CON CATÁLOGO", "status": "PASS" if not errores else "INFO",
                            "score": False, "summary": resumen_ok, "headers": COLUMNAS, "rows": _tabla(ok),
                            "val": [vpor.get(id(f)) for f in ok], "val_card": hay_val})

        def _val_txt(lst):
            n = sum(1 for f in lst if (vpor.get(id(f)) or {}).get("o", f[10]) != f[10])
            return f" · {n} con estatus validado manualmente" if n else ""
        for motivo, lst in sorted(motivos.items(), key=lambda x: (-len(x[1]), x[0])):
            results.append({"section": titulo, "name": motivo.upper(), "status": "FAIL", "score": False,
                            "summary": f"{len(lst)} concepto{'s' if len(lst) != 1 else ''}: {motivo}.{_val_txt(lst)}",
                            "headers": COLUMNAS, "rows": _tabla(lst), "val": [vpor.get(id(f)) for f in lst],
                            "cmp": [comparacion(f, catalogos) for f in lst],
                            "resaltar": resaltar(motivo), "val_card": hay_val})
        if review or hay_val:
            results.append({"section": titulo, "name": REVIEW_CARD, "status": "INFO",
                            "score": False, "summary": f"{len(review)} concepto{'s' if len(review) != 1 else ''} con código especial: "
                                                        "modificación del proyecto, requiere revisión visual. Cuentan como Review." + _val_txt(review),
                            "headers": COLUMNAS, "rows": _tabla(review), "val": [vpor.get(id(f)) for f in review],
                            "resaltar": ["Código"], "resaltar_tono": "rev", "val_card": hay_val})
        if manual or any((vpor.get(id(f)) or {}).get("o") in ("OK", "REVIEW") for f in del_alcance):
            results.append({"section": titulo, "name": MANUAL_ERR, "status": "FAIL", "score": False,
                            "summary": f"{len(manual)} concepto{'s' if len(manual) != 1 else ''} marcados como Error en la revisión manual.",
                            "headers": COLUMNAS, "rows": _tabla(manual), "val": [vpor.get(id(f)) for f in manual],
                            "cmp": [comparacion(f, catalogos) for f in manual], "val_card": True})
    con_blancos = [f for f in filas if f[12]]
    residuos = [f for f in filas if f[13]]

    # Conceptos validados como OK en otro recuadro: dejan de mostrarse aqui (siguen en la pagina, ocultos,
    # por si se regresan a Error o Review)
    def _validado_ok(f):
        v = vpor.get(id(f))
        return bool(v) and v["e"] == "OK" and v["o"] != "OK"

    def _ref(lst):
        return [(vpor.get(id(f)) or {}).get("h") for f in lst]

    vis_b = sum(1 for f in con_blancos if not _validado_ok(f))
    vis_r = sum(1 for f in residuos if not _validado_ok(f))
    results.append({"section": "CAPTURA", "name": "PARÁMETROS CAPTURADOS", "status": "PASS" if pct_par >= 95 else "FAIL",
                    "score": False, "summary": f"{pct_par}% capturados · {capt} capturados, {blanc} en blanco.",
                    "headers": [], "rows": []})
    results.append({"section": "CAPTURA", "name": "CONCEPTOS CON CAMPOS EN BLANCO", "status": "FAIL" if vis_b else "PASS",
                    "score": False, "summary": f"Conceptos con algún campo en blanco: {vis_b}",
                    "headers": COLUMNAS + ["Campos en blanco"], "rows": _tabla(con_blancos, con_blancos=True),
                    "resaltar": ["Campos en blanco"], "ref": _ref(con_blancos),
                    "ocultas": [_validado_ok(f) for f in con_blancos], "visibles": vis_b})
    results.append({"section": "CAPTURA", "name": "POSIBLES RESIDUOS AISLADOS", "status": "INFO" if vis_r else "PASS",
                    "score": False, "summary": f"Grupos con un solo dato capturado: {vis_r}. No suman al % de captura, "
                                               "pero conviene revisarlos.", "headers": COLUMNAS, "rows": _tabla(residuos),
                    "ref": _ref(residuos), "ocultas": [_validado_ok(f) for f in residuos], "visibles": vis_r})
    for r in results:  # identidad y firma de cada recuadro (marca "Revisado")
        r["key"] = f"{r['section']}|{r['name']}"
        r["sig"] = validacion5d.firma(r["rows"] or r["summary"])
    return results, pct_par


def construir(grupos, catalogo, personas, cfg, tz):
    max_ok = cfg.get("max_filas_ok_por_tarjeta", 2000)
    """-> (modelos, avisos). Un elemento por modelo-mes que entra al reporte."""
    modelos, avisos = [], []
    fuera_catalogo, sin_integrante = Counter(), Counter()
    for (mes, iid), regs in sorted(grupos.items()):
        cat = catalogo.get(iid)
        if not cat:
            fuera_catalogo[modelo_sin_ext(regs[0].get("modelo"))] += 1
            continue

        participantes, resp = comun.participantes(regs, personas)
        if not resp:
            sin_integrante[f"{cat['modelo']} ({mes})"] += 1
            continue

        # Resultado del mes: la auditoria de la ULTIMA sincronizacion (de quien sea)
        con_aud = [r for r in regs if (r.get("modulos") or {}).get(ID)]
        if not con_aud:
            avisos.append(f"{cat['modelo']} ({mes}): sincronizado pero sin revision 5D guardada.")
            continue
        ultimo = max(con_aud, key=lambda r: r["_ultima"] or datetime.min)
        aud = ultimo["modulos"][ID]
        fecha_aud = parse_fecha(aud.get("fecha"), tz) or ultimo["_ultima"]
        # Validaciones manuales guardadas (Review y conceptos sin Control) -> se aplican al % oficial
        decisiones = validacion5d.leer(cfg.get("_carpeta_5d"), iid)
        filas_orig = aud.get("filas") or []
        filas_val, vals, aplicadas, ignoradas = validacion5d.aplicar(filas_orig, decisiones)
        c0, c1 = validacion5d.conteos(filas_orig), validacion5d.conteos(filas_val)
        t = aud.get("totales") or {}
        ok = int(t.get("ok", 0)) + c1["OK"] - c0["OK"]
        err = int(t.get("error", 0)) + c1["ERROR"] - c0["ERROR"]
        revw = int(t.get("review", 0)) + c1["REVIEW"] - c0["REVIEW"]
        evaluados = ok + err + revw
        catalogos = None
        if aud.get("catalogo") and cfg.get("_carpeta_5d"):
            ruta_cat = Path(cfg["_carpeta_5d"]) / aud["catalogo"]
            try:
                catalogos = catalogo_bd.leer(ruta_cat) if ruta_cat.exists() else None
            except Exception as ex:
                avisos.append(f"No se pudo leer el catálogo {aud['catalogo']}: {str(ex)[:80]}")
        results, pct_par = a_results({**aud, "filas": filas_val}, max_ok, vals, catalogos)
        # La marca "Revisado" se firma con el contenido SIN validaciones manuales: validar no la invalida,
        # solo un cambio en Revit.
        firmas = {r["key"]: r["sig"] for r in a_results({**aud, "filas": filas_orig}, max_ok)[0]}
        for r in results:
            r["sig"] = firmas.get(r["key"], r["sig"])
        if decisiones:
            results.insert(2, {"section": "RESUMEN", "name": "VALIDACIONES MANUALES", "status": "INFO", "score": False,
                               "summary": f"{aplicadas} concepto(s) con estatus validado manualmente"
                                          + (f" · {ignoradas} validación(es) ya no aplican: el concepto cambió en Revit" if ignoradas else "")
                                          + ".", "headers": [], "rows": []})
        modelos.append({
            **comun.base_modelo(mes, iid, cat),
            "responsable": resp["integrante"], "equipo": resp["equipo"],
            "participantes": comun.participantes_json(participantes),
            "syncs": sum(p["syncs"] for p in participantes),
            "fecha": fecha_aud.isoformat(timespec="minutes") if fecha_aud else "",
            "duracion_s": aud.get("duracion_s"),
            "evaluados": evaluados, "ok": ok, "error": err, "review": revw,
            "percent": int(round(100.0 * ok / evaluados)) if evaluados else 0,
            "pct_parametros": pct_par, "vista": aud.get("vista") or "", "sin_vista": bool(aud.get("aviso")),
            "validadas": aplicadas,
            "results": results,
            "val_meta": {"modelo": cat["modelo"], "item_id": iid, "archivo": validacion5d.archivo("", iid).name,
                         "base": {"OK": ok, "REVIEW": revw, "ERROR": err},
                         "revisados": validacion5d.leer_revisados(cfg.get("_carpeta_5d"), iid)},
        })
    if fuera_catalogo:
        avisos.append("Revisiones 5D de modelos que no estan en 011_WIP de VENTAS (no cuentan): "
                      + ", ".join(sorted(fuera_catalogo)))
    if sin_integrante:
        avisos.append("Modelos sincronizados solo por personas fuera del listado (no cuentan): "
                      + ", ".join(sorted(sin_integrante)))
    return modelos, avisos


def pagina(mes, proyecto, modelos, cfg):
    modelos = sorted(modelos, key=lambda m: m["modelo"])
    ultima = max((datetime.fromisoformat(m["fecha"]) for m in modelos if m["fecha"]), default=None)
    reports = [{
        "name": m["modelo"],
        "path": f"Responsable: {m['responsable']} · {m['syncs']} sincronizaciones en el mes",
        "kind": "HOST",
        "kind_label": m["disciplina"],
        "results": m["results"],
        "percent_fijo": m["percent"],
        "failed_fijo": m["error"] + m["review"] + (1 if m["sin_vista"] else 0),
        "responsable": m["responsable"],
        "participantes": m["participantes"],
        "fecha_auditoria": datetime.fromisoformat(m["fecha"]).strftime("%d/%m/%Y %H:%M") if m["fecha"] else "",
        "val_meta": m.get("val_meta"),
    } for m in modelos]
    raiz = (cfg.get("raiz_nombres") or ["Project Files"])[0]
    ruta = f"{cfg.get('proyecto_acc', 'VENTAS GCP')} / {raiz} / {proyecto} · {mes}"
    ok = sum(m["ok"] for m in modelos)
    err = sum(m["error"] for m in modelos)
    revw = sum(m["review"] for m in modelos)
    ev = ok + err + revw
    pct = int(round(100.0 * ok / ev)) if ev else 0
    resumen = {
        "titulo": "Base de Datos vs Revit.", "subtitulo": "Conceptos 5D.",
        "copy": "Revisa que los conceptos usados en Revit coincidan con la Base de Datos de Presupuestos: "
                "código, control, descripción, unidad y partida de cada concepto Base, AC, REC y ADD.",
        "percent": pct, "score_label": "% OK",
        "score_class": "score-red" if pct <= 70 else "score-orange" if pct < 95 else "score-green",
        "caption": f"{ok} de {ev} conceptos coinciden<br>con la Base de Datos.",
        "metricas": [("Modelos revisados", len(modelos), "total"), ("Conceptos evaluados", ev, "total"),
                     ("OK", ok, "pass"), ("Errores / Review", f"{err} / {revw}", "fail")],
    }
    return build_html(proyecto, ruta, comun.fecha_larga(ultima), reports, resumen=resumen,
                      extra_css=validacion5d.ESTILO, extra_script=validacion5d.SCRIPT,
                      footer_note=f"Revisión 5D automática al sincronizar (Sync5D) · última del mes · {comun.fecha_larga(ultima)}")


