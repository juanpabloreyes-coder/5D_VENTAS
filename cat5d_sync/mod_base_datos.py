"""Modulo "Base de Datos vs Revit": conceptos de Revit contra la Base de Datos de Presupuestos.
Corre en Revit al sincronizar (add-in Sync5D, Catalogo5D.cs) con el catalogo PPTO MAESTRO de 03374_5D_VENTAS
y la vista 3D "ACC" del modelo; aqui se toma, por modelo y mes, la revision de la ULTIMA sincronizacion.
% OK = OK / (OK + Errores + Review), igual que el boton. Los codigos 1111111111 cuentan como Review."""
from collections import Counter
from datetime import datetime

from . import comun
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


def a_results(rev, max_ok):
    """Convierte la revision 5D del add-in en tarjetas con la forma del Checker:
    una seccion por alcance (Base / AC / REC / ADD) con una tarjeta de coincidencias, una por cada
    motivo de error y una de revision manual; y una seccion de captura de parametros."""
    filas = rev.get("filas") or []
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
        ok = [f for f in del_alcance if f[10] == "OK"]
        review = [f for f in del_alcance if f[10] == "REVIEW"]
        errores = [f for f in del_alcance if f[10] not in ("OK", "REVIEW")]
        resumen_ok = f"{len(ok)} de {len(del_alcance)} conceptos coinciden con el catálogo."
        filas_ok = _tabla(ok)
        if len(filas_ok) > max_ok:
            resumen_ok += f" (se muestran los primeros {max_ok})"
            filas_ok = filas_ok[:max_ok]
        results.append({"section": titulo, "name": "COINCIDEN CON CATÁLOGO", "status": "PASS" if not errores else "INFO",
                        "score": False, "summary": resumen_ok, "headers": COLUMNAS, "rows": filas_ok})
        motivos = {}
        for f in errores:
            motivos.setdefault(f[11], []).append(f)
        for motivo, lst in sorted(motivos.items(), key=lambda x: (-len(x[1]), x[0])):
            results.append({"section": titulo, "name": motivo.upper(), "status": "FAIL", "score": False,
                            "summary": f"{len(lst)} concepto{'s' if len(lst) != 1 else ''}: {motivo}.",
                            "headers": COLUMNAS, "rows": _tabla(lst)})
        if review:
            results.append({"section": titulo, "name": "REVISIÓN MANUAL (CÓDIGO 1111111111)", "status": "INFO",
                            "score": False, "summary": f"{len(review)} concepto{'s' if len(review) != 1 else ''} con código especial: "
                                                        "modificación del proyecto, requiere revisión visual. Cuentan como Review.",
                            "headers": COLUMNAS, "rows": _tabla(review)})
    con_blancos = [f for f in filas if f[12]]
    residuos = [f for f in filas if f[13]]
    results.append({"section": "CAPTURA", "name": "PARÁMETROS CAPTURADOS", "status": "PASS" if pct_par >= 95 else "FAIL",
                    "score": False, "summary": f"{pct_par}% capturados · {capt} capturados, {blanc} en blanco.",
                    "headers": [], "rows": []})
    results.append({"section": "CAPTURA", "name": "CONCEPTOS CON CAMPOS EN BLANCO", "status": "FAIL" if con_blancos else "PASS",
                    "score": False, "summary": f"Conceptos con algún campo en blanco: {len(con_blancos)}",
                    "headers": COLUMNAS + ["Campos en blanco"], "rows": _tabla(con_blancos, con_blancos=True)})
    results.append({"section": "CAPTURA", "name": "POSIBLES RESIDUOS AISLADOS", "status": "INFO" if residuos else "PASS",
                    "score": False, "summary": f"Grupos con un solo dato capturado: {len(residuos)}. No suman al % de captura, "
                                               "pero conviene revisarlos.", "headers": COLUMNAS, "rows": _tabla(residuos)})
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
        results, pct_par = a_results(aud, max_ok)
        t = aud.get("totales") or {}
        ok, err, revw = int(t.get("ok", 0)), int(t.get("error", 0)), int(t.get("review", 0))
        evaluados = ok + err + revw
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
            "results": results,
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
                      footer_note=f"Revisión 5D automática al sincronizar (Sync5D) · última del mes · {comun.fecha_larga(ultima)}")


