# -*- coding: utf-8 -*-
"""HTML de un proyecto con el MISMO diseno del Checker (GCPTools > Salud del Modelo > script.py,
funcion build_html). Copiado tal cual; solo cambia de donde salen los datos: en vez del documento
abierto en Revit, recibe los modelos del proyecto con su ultima auditoria del mes (del add-in
AuditSync), su responsable y sus participantes."""


def safe_str(value):
    try:
        if value is None:
            return ""
        return str(value)
    except Exception:
        return ""


def html_escape(text):
    text = safe_str(text)
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))


def diff_html(a, b, ignorar_mayusculas=False):
    """Resalta los caracteres distintos entre dos textos -> (html_a, html_b)."""
    import difflib
    a, b = safe_str(a), safe_str(b)
    if a in ("(vacío)", "") or b in ("(vacío)", ""):
        ma = '<mark class="dx">{}</mark>'.format(html_escape(a)) if a and a != "(vacío)" else html_escape(a)
        mb = '<mark class="dx">{}</mark>'.format(html_escape(b)) if b and b != "(vacío)" else html_escape(b)
        return ma, mb
    ua, ub = (a.upper(), b.upper()) if ignorar_mayusculas else (a, b)
    if len(ua) != len(a) or len(ub) != len(b):
        ua, ub = a, b
    sm = difflib.SequenceMatcher(None, ua, ub, autojunk=False)
    pa, pb = [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            pa.append(html_escape(a[i1:i2])); pb.append(html_escape(b[j1:j2]))
        else:
            if i2 > i1:
                pa.append('<mark class="dx">{}</mark>'.format(html_escape(a[i1:i2])))
            if j2 > j1:
                pb.append('<mark class="dx">{}</mark>'.format(html_escape(b[j1:j2])))
    return "".join(pa), "".join(pb)


def make_table(headers, rows, val=None, resaltar=None, tono="", diff=None, forzar=False, cmp=None, ref=None, ocultas=None):
    if not rows and not forzar:
        return "<p>Sin resultados.</p>"
    ia = headers.index(diff[0]) if diff and diff[0] in headers else None
    ib = headers.index(diff[1]) if diff and diff[1] in headers else None
    con_val = forzar or (bool(val) and any(val))
    hl = set(resaltar or [])
    clase_hl = ' class="hl{}"'.format(" hl-rev" if tono == "rev" else "")

    parts = []
    parts.append("<table>")
    parts.append("<tr>")
    if con_val:
        parts.append("<th></th><th>Estatus</th>")
    # Comparacion (diff): las dos columnas se apilan en una sola celda, Revit arriba, como en Base de Datos vs Revit
    pila = ia is not None and ib is not None
    if pila:
        arriba, abajo = (ia, ib) if headers[ia] == "Revit" or headers[ib] != "Revit" else (ib, ia)
        p1, p2 = min(ia, ib), max(ia, ib)
    for k, h in enumerate(headers):
        if pila and k == p2:
            continue
        if pila and k == p1:
            parts.append('<th class="hl dxcol">{} vs {}</th>'.format(html_escape(headers[arriba]), html_escape(headers[abajo])))
            continue
        cls = clase_hl if h in hl else ""
        parts.append("<th{}>{}</th>".format(cls, html_escape(h)))
    parts.append("</tr>")

    for i, row in enumerate(rows):
        v = val[i] if con_val and i < len(val) else None
        if v:
            tags = ('<span class="val-tag">Review</span>' if v.get("rev") else "") + \
                   ('<span class="val-tag">Sin Control</span>' if v.get("sc") else "")
            extra = ""
            for k_attr, k_val in (("g", "g"), ("sec", "sec"), ("home", "home")):
                if v.get(k_val):
                    extra += ' data-{}="{}"'.format(k_attr, html_escape(v[k_val]))
            parts.append('<tr class="val-row st-{e}" data-h="{h}" data-o="{o}" data-e0="{e}"{x}>'.format(
                e=html_escape(v["e"]), h=html_escape(v["h"]), o=html_escape(v["o"]), x=extra))
            parts.append('<td><input type="checkbox" class="val-sel" aria-label="Seleccionar concepto"></td><td><div class="val-cell"><select class="val-st" aria-label="Estatus">'
                         '<option value="OK">OK</option><option value="REVIEW">Review</option>'
                         '<option value="ERROR">Error</option></select>{}</div></td>'.format('<div class="val-tags">{}</div>'.format(tags) if tags else ""))
        else:
            rf = ref[i] if ref and i < len(ref) else None
            oc = bool(ocultas and i < len(ocultas) and ocultas[i])
            parts.append("<tr{}{}>".format(' data-ref="{}"'.format(html_escape(rf)) if rf else "",
                                           ' style="display:none"' if oc else ""))
            if con_val:
                parts.append("<td></td><td></td>")
        dif = diff_html(row[ia], row[ib]) if ia is not None and ib is not None and ia < len(row) and ib < len(row) else None
        cm = cmp[i] if cmp and i < len(cmp) and cmp[i] else {}
        for j, c in enumerate(row):
            if j in cm:
                x = cm[j]
                if x.get("diff"):
                    ra, rc = diff_html(c, x["v"], ignorar_mayusculas=True)
                else:
                    ra, rc = html_escape(c) or "—", html_escape(x["v"])
                parts.append('<td class="cmpcell"><div class="cmp"><span class="cmp-r"><em>Revit</em>{}</span>'
                             '<span class="cmp-c"><em>Catálogo</em>{}</span></div></td>'.format(ra or "—", rc))
                continue
            if pila and j == p2:
                continue
            if pila and j == p1:
                if dif:
                    tx = {ia: dif[0], ib: dif[1]}
                else:
                    tx = {ia: html_escape(row[ia]) if ia < len(row) else "", ib: html_escape(row[ib]) if ib < len(row) else ""}
                parts.append('<td class="cmpcell dxcell"><div class="cmp"><span class="cmp-r"><em>{}</em>{}</span>'
                             '<span class="cmp-c"><em>{}</em>{}</span></div></td>'.format(
                                 html_escape(headers[arriba]), tx[arriba] or "—", html_escape(headers[abajo]), tx[abajo] or "—"))
                continue
            marcar = j < len(headers) and headers[j] in hl
            if marcar:
                parts.append('<td{}><span class="hl-chip">{}</span></td>'.format(clase_hl, html_escape(c) if c not in (None, "") else "—"))
            else:
                parts.append("<td>{}</td>".format(html_escape(c)))
        parts.append("</tr>")
    parts.append("</table>")
    return "".join(parts)


def build_html(project_name, file_path, report_date, model_reports, unavailable_links=None, footer_note="", resumen=None,
               extra_css="", extra_script=""):
    """model_reports: [{name, path, kind_label, results, participantes:[{integrante, equipo, syncs}], responsable}]"""
    unavailable_links = unavailable_links or []

    all_results = []
    for report in model_reports:
        report_results = report.get("results", [])
        all_results.extend(report_results)
        report_score_items = [r for r in report_results if r["score"] and r["status"] in ["PASS", "FAIL"]]
        report_total = len(report_score_items)
        report_passed = len([r for r in report_score_items if r["status"] == "PASS"])
        report_failed = len([r for r in report_score_items if r["status"] == "FAIL"])
        report["total"] = report_total
        report["passed"] = report_passed
        report["failed"] = report_failed
        report["percent"] = int(round((float(report_passed) / report_total) * 100)) if report_total > 0 else 0
        # 5D: el % del modelo es % OK de conceptos (no de checks)
        if report.get("percent_fijo") is not None:
            report["percent"] = report["percent_fijo"]
            report["failed"] = report.get("failed_fijo", report["failed"])

    score_items = [r for r in all_results if r["score"] and r["status"] in ["PASS", "FAIL"]]
    total = len(score_items)
    passed = len([r for r in score_items if r["status"] == "PASS"])
    failed = len([r for r in score_items if r["status"] == "FAIL"])
    percent = int(round((float(passed) / total) * 100)) if total > 0 else 0
    model_count = len(model_reports)
    resumen = resumen or {}
    if resumen.get("percent") is not None:
        percent = resumen["percent"]

    if percent <= 69:
        score_class = "score-red"
    elif percent <= 79:
        score_class = "score-orange"
    else:
        score_class = "score-green"
    if resumen.get("score_class"):
        score_class = resumen["score_class"]


    sections = []
    for r in all_results:
        if r["section"] not in sections:
            sections.append(r["section"])

    def svg_icon(path_markup, css_class=""):
        return ('<svg class="{}" viewBox="0 0 24 24" fill="none" '
                'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" '
                'stroke-linejoin="round" aria-hidden="true">{}</svg>').format(
                    css_class, path_markup)

    home_icon = svg_icon(
        '<rect x="4" y="4" width="6" height="6" rx="1.5"></rect>'
        '<rect x="14" y="4" width="6" height="6" rx="1.5"></rect>'
        '<rect x="4" y="14" width="6" height="6" rx="1.5"></rect>'
        '<rect x="14" y="14" width="6" height="6" rx="1.5"></rect>'
    )

    section_icons = {
        "GENERAL": svg_icon('<path d="M4 13a8 8 0 1 1 16 0"></path><path d="m12 13 4-4"></path><path d="M7 18h10"></path>'),
        "MODEL": svg_icon('<path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z"></path><path d="m4.5 7.8 7.5 4.1 7.5-4.1"></path><path d="M12 12v9"></path>'),
        "LINKS / CAD": svg_icon('<path d="M9.5 14.5 14.5 9"></path><path d="M7.2 17.3 5.7 18.8a3.5 3.5 0 0 1-5-5l3-3a3.5 3.5 0 0 1 5 0"></path><path d="m16.8 6.7 1.5-1.5a3.5 3.5 0 0 1 5 5l-3 3a3.5 3.5 0 0 1-5 0"></path>'),
        "WORKSETS": svg_icon('<path d="m12 3 9 5-9 5-9-5 9-5Z"></path><path d="m3 12 9 5 9-5"></path><path d="m3 16 9 5 9-5"></path>'),
        "ROOMS / AREAS": svg_icon('<rect x="3" y="3" width="18" height="18" rx="3"></rect><path d="M3 10h8V3"></path><path d="M11 10v11"></path><path d="M11 15h10"></path>'),
        "VIEWS / DOCUMENTATION": svg_icon('<path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"></path><circle cx="12" cy="12" r="2.5"></circle>'),
        "MODEL QUALITY": svg_icon('<path d="m5 12 4 4L19 6"></path><path d="M20 13a8 8 0 1 1-5-8"></path>'),
        "MEP": svg_icon('<path d="m13 2-7 11h6l-1 9 7-12h-6l1-8Z"></path>'),
        # 5D
        "RESUMEN": svg_icon('<path d="M4 13a8 8 0 1 1 16 0"></path><path d="m12 13 4-4"></path><path d="M7 18h10"></path>'),
        "CONCEPTO BASE": svg_icon('<rect x="4" y="3" width="16" height="18" rx="2"></rect><path d="M8 8h8M8 12h8M8 16h5"></path>'),
        "AC": svg_icon('<path d="M4 20h16"></path><path d="M6 16 14 8l2 2-8 8H6v-2Z"></path>'),
        "REC": svg_icon('<rect x="3" y="3" width="18" height="18" rx="3"></rect><path d="M3 9h18M9 21V9"></path>'),
        "ADD": svg_icon('<circle cx="12" cy="12" r="9"></circle><path d="M12 8v8M8 12h8"></path>'),
        "INTEGRIDAD": svg_icon('<path d="M12 3 5 6v6c0 4.2 3 7.6 7 9 4-1.4 7-4.8 7-9V6l-7-3Z"></path><path d="m9 12 2 2 4-4"></path>'),
        "VIGENCIA": svg_icon('<path d="M3 12a9 9 0 1 0 3-6.7"></path><path d="M3 4v4h4"></path><path d="M12 8v4l3 2"></path>'),
        "CAPTURA": svg_icon('<path d="M4 7V5a1 1 0 0 1 1-1h2M17 4h2a1 1 0 0 1 1 1v2M20 17v2a1 1 0 0 1-1 1h-2M7 20H5a1 1 0 0 1-1-1v-2"></path><path d="m8 12 3 3 5-6"></path>')
    }

    parts = []
    parts.append("""<!doctype html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="light">
    <title>5D · Base de Datos vs Revit</title>
    <style>
        :root {
            --page: #f5f5f7;
            --surface: #fff;
            --primary: #1d1d1f;
            --secondary: #424245;
            --tertiary: #86868b;
            --blue: #007aff;
            --purple: #af52de;
            --teal: #30b0c7;
            --gray: #8e8e93;
            --orange: #ff9500;
            --red: #ff3b30;
            --line: rgba(0, 0, 0, .06);
            --control: rgba(120, 120, 128, .12);
            --shadow: 0 1px 2px rgba(0, 0, 0, .04), 0 8px 24px rgba(0, 0, 0, .06);
            --spring: cubic-bezier(.2, .85, .25, 1.15);
        }

        * { box-sizing: border-box; }
        html { scroll-behavior: smooth; scroll-padding-top: 122px; }
        body {
            margin: 0;
            min-width: 320px;
            background: var(--page);
            color: var(--primary);
            font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", Inter, sans-serif;
            -webkit-font-smoothing: antialiased;
            text-rendering: optimizeLegibility;
        }
        button, input { font: inherit; }
        button { color: inherit; }
        a { color: inherit; }
        svg { width: 22px; height: 22px; display: block; }

        .dock-shell {
            position: fixed;
            z-index: 1000;
            top: 18px;
            left: 50%;
            transform: translateX(-50%);
            max-width: calc(100vw - 24px);
        }
        .dock {
            display: flex;
            align-items: flex-start;
            gap: 4px;
            padding: 8px 10px 9px;
            overflow: visible;
            border: 1px solid rgba(0, 0, 0, .08);
            border-radius: 22px;
            background: rgba(255, 255, 255, .72);
            box-shadow: 0 8px 32px rgba(0, 0, 0, .09), inset 0 1px 0 rgba(255, 255, 255, .7);
            -webkit-backdrop-filter: blur(30px) saturate(180%);
            backdrop-filter: blur(30px) saturate(180%);
        }
        .dock-item {
            position: relative;
            display: grid;
            width: 42px;
            height: 42px;
            flex: 0 0 42px;
            place-items: center;
            border-radius: 13px;
            color: #6e6e73;
            text-decoration: none;
            transform-origin: center top;
            transition: color .22s ease, background .22s ease, transform .1s ease-out;
            will-change: transform;
        }
        .dock-item:hover { color: var(--primary); background: rgba(120, 120, 128, .09); }
        .dock-item.active { color: var(--blue); background: rgba(0, 122, 255, .11); }
        .dock-item.active::after {
            content: "";
            position: absolute;
            left: 50%;
            bottom: -6px;
            width: 4px;
            height: 4px;
            transform: translateX(-50%);
            border-radius: 50%;
            background: var(--blue);
            box-shadow: 0 0 0 2px rgba(255, 255, 255, .82);
        }
        .dock-tooltip {
            position: absolute;
            left: 50%;
            top: calc(100% + 14px);
            width: max-content;
            max-width: 190px;
            padding: 6px 9px;
            transform: translate(-50%, -4px) scale(.96);
            border: 1px solid rgba(0, 0, 0, .08);
            border-radius: 8px;
            background: rgba(255, 255, 255, .9);
            box-shadow: 0 5px 18px rgba(0, 0, 0, .12);
            color: var(--secondary);
            font-size: 11px;
            font-weight: 600;
            line-height: 1.2;
            text-align: center;
            opacity: 0;
            pointer-events: none;
            transition: opacity .16s ease, transform .2s var(--spring);
            -webkit-backdrop-filter: blur(18px);
            backdrop-filter: blur(18px);
        }
        .dock-item:hover .dock-tooltip,
        .dock-item:focus-visible .dock-tooltip { opacity: 1; transform: translate(-50%, 0) scale(1); }

        .page { width: min(1180px, calc(100% - 40px)); margin: 0 auto; padding: 132px 0 80px; }
        .hero {
            display: grid;
            grid-template-columns: minmax(0, 1.5fr) minmax(280px, .7fr);
            gap: 48px;
            align-items: center;
            min-height: 390px;
            padding: 54px 58px;
            overflow: hidden;
            border: 1px solid var(--line);
            border-radius: 28px;
            background: var(--surface);
            box-shadow: var(--shadow);
        }
        .eyebrow {
            display: flex;
            align-items: center;
            gap: 8px;
            margin: 0 0 18px;
            color: var(--tertiary);
            font-size: 12px;
            font-weight: 700;
            letter-spacing: .08em;
            text-transform: uppercase;
        }
        .eyebrow-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--teal); box-shadow: 0 0 0 5px rgba(48, 176, 199, .12); }
        h1 {
            margin: 0;
            font-size: clamp(42px, 5vw, 66px);
            font-weight: 700;
            letter-spacing: -.04em;
            line-height: 1.02;
        }
        h1 span { display: block; }
        .gradient-title {
            padding-bottom: .08em;
            background: linear-gradient(100deg, var(--blue), var(--purple));
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
        }
        .health-title { margin-top: .28em; font-size: .56em; letter-spacing: -.025em; line-height: 1.08; }
        .hero-copy { max-width: 640px; margin: 24px 0 0; color: var(--secondary); font-size: 17px; line-height: 1.5; }
        .file-meta { display: grid; gap: 7px; margin-top: 30px; color: var(--tertiary); font-size: 12px; line-height: 1.45; }
        .file-meta-row { display: flex; gap: 8px; align-items: flex-start; min-width: 0; }
        .file-meta-row svg { width: 15px; height: 15px; margin-top: 1px; flex: 0 0 auto; }
        .file-path { overflow-wrap: anywhere; }

        .score-panel { display: grid; justify-items: center; gap: 22px; }
        .score-ring {
            --score-color: var(--teal);
            position: relative;
            display: grid;
            width: 210px;
            height: 210px;
            place-items: center;
            border-radius: 50%;
            background: conic-gradient(var(--score-color) calc(var(--score) * 1%), rgba(120, 120, 128, .11) 0);
            box-shadow: inset 0 0 0 1px rgba(0, 0, 0, .03), 0 12px 32px rgba(0, 0, 0, .08);
        }
        .score-ring::before { content: ""; position: absolute; inset: 13px; border-radius: 50%; background: #fff; box-shadow: inset 0 1px 3px rgba(0, 0, 0, .05); }
        .score-red { --score-color: var(--red); }
        .score-orange { --score-color: var(--orange); }
        .score-green { --score-color: var(--teal); }
        .score-value { position: relative; text-align: center; }
        .score-number { display: block; font-size: 58px; font-weight: 700; letter-spacing: -.055em; line-height: 1; color: var(--primary); }
        .score-label { display: block; margin-top: 7px; color: var(--tertiary); font-size: 12px; font-weight: 650; letter-spacing: .02em; }
        .score-caption { margin: 0; color: var(--secondary); font-size: 13px; text-align: center; }

        .metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin: 14px 0 28px; }
        .metric {
            min-height: 126px;
            padding: 24px 26px;
            border: 1px solid var(--line);
            border-radius: 20px;
            background: var(--surface);
            box-shadow: var(--shadow);
        }
        .metric-label { display: flex; align-items: center; gap: 8px; color: var(--tertiary); font-size: 12px; font-weight: 650; }
        .metric-label::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
        .metric.pass .metric-label { color: var(--teal); }
        .metric.fail .metric-label { color: var(--red); }
        .metric.total .metric-label { color: var(--blue); }
        .metric-number { margin-top: 11px; font-size: 34px; font-weight: 700; letter-spacing: -.035em; line-height: 1; }

        .models-panel {
            margin-bottom: 34px;
            padding: 26px;
            border: 1px solid var(--line);
            border-radius: 22px;
            background: var(--surface);
            box-shadow: var(--shadow);
        }
        .models-panel-head { display: flex; align-items: end; justify-content: space-between; gap: 18px; margin-bottom: 17px; }
        .models-panel-title { margin: 0; font-size: 20px; font-weight: 700; letter-spacing: -.025em; }
        .models-panel-copy { margin: 6px 0 0; color: var(--tertiary); font-size: 12px; line-height: 1.45; }
        .model-tabs { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
        .model-option {
            position: relative;
            display: grid;
            grid-template-columns: 42px minmax(0, 1fr) auto;
            gap: 12px;
            align-items: center;
            min-width: 0;
            padding: 13px;
            border: 1px solid rgba(0, 0, 0, .07);
            border-radius: 16px;
            background: #fafafd;
            color: var(--primary);
            text-align: left;
            cursor: pointer;
            transition: transform .25s var(--spring), background .2s ease, border-color .2s ease, box-shadow .2s ease;
        }
        .model-option:hover { transform: translateY(-2px); background: #fff; border-color: rgba(0, 0, 0, .12); }
        .model-option.active { border-color: rgba(0, 122, 255, .28); background: rgba(0, 122, 255, .055); box-shadow: 0 0 0 3px rgba(0, 122, 255, .08); }
        .model-option-icon { display: grid; width: 42px; height: 42px; place-items: center; border-radius: 13px; background: rgba(0, 122, 255, .1); color: var(--blue); }
        .model-option.link .model-option-icon { background: rgba(175, 82, 222, .1); color: var(--purple); }
        .model-option-icon svg { width: 20px; height: 20px; }
        .model-option-copy { min-width: 0; }
        .model-option-kind { display: block; margin-bottom: 4px; color: var(--tertiary); font-size: 9px; font-weight: 750; letter-spacing: .075em; text-transform: uppercase; }
        .model-option-name { display: block; overflow: hidden; color: var(--primary); font-size: 13px; font-weight: 680; line-height: 1.25; text-overflow: ellipsis; white-space: nowrap; }
        .model-option-path { display: block; margin-top: 4px; overflow: hidden; color: var(--tertiary); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
        .model-option-score { display: grid; width: 42px; height: 42px; place-items: center; border-radius: 50%; background: var(--control); color: var(--secondary); font-size: 11px; font-weight: 750; font-variant-numeric: tabular-nums; }
        .model-option.has-failures .model-option-score { background: rgba(255, 59, 48, .1); color: var(--red); }
        .model-option.no-failures .model-option-score { background: rgba(48, 176, 199, .11); color: var(--teal); }
        .unavailable-note { display: flex; gap: 9px; align-items: flex-start; margin-top: 14px; padding: 11px 13px; border-radius: 13px; background: rgba(255, 149, 0, .09); color: #9a5b00; font-size: 11px; line-height: 1.45; }
        .unavailable-note svg { width: 17px; height: 17px; flex: 0 0 auto; }
        .model-report { display: none; }
        .model-report.active { display: block; }

        .toolbar {
            position: sticky;
            z-index: 100;
            top: 86px;
            display: flex;
            gap: 12px;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 44px;
            padding: 10px;
            border: 1px solid rgba(0, 0, 0, .06);
            border-radius: 20px;
            background: rgba(245, 245, 247, .78);
            -webkit-backdrop-filter: blur(24px) saturate(160%);
            backdrop-filter: blur(24px) saturate(160%);
        }
        .search-wrap { position: relative; flex: 1 1 320px; max-width: 470px; }
        .search-wrap > svg { position: absolute; left: 14px; top: 50%; width: 18px; height: 18px; transform: translateY(-50%); color: var(--tertiary); pointer-events: none; }
        .search-input {
            width: 100%;
            height: 42px;
            padding: 0 42px;
            border: 0;
            border-radius: 999px;
            outline: 0;
            background: var(--control);
            color: var(--primary);
            font-size: 14px;
            transition: box-shadow .2s ease, background .2s ease;
        }
        .search-input::placeholder { color: var(--tertiary); }
        .search-input:focus { background: rgba(120, 120, 128, .09); box-shadow: 0 0 0 3px rgba(0, 122, 255, .16); }
        .clear-search {
            position: absolute;
            right: 8px;
            top: 50%;
            display: grid;
            width: 28px;
            height: 28px;
            padding: 0;
            transform: translateY(-50%);
            place-items: center;
            border: 0;
            border-radius: 50%;
            background: transparent;
            color: var(--tertiary);
            cursor: pointer;
            opacity: 0;
            pointer-events: none;
        }
        .clear-search.visible { opacity: 1; pointer-events: auto; }
        .clear-search svg { width: 15px; height: 15px; }
        .toolbar-actions { display: flex; gap: 8px; align-items: center; }
        .segmented { display: flex; gap: 2px; padding: 3px; border-radius: 999px; background: var(--control); }
        .segment {
            min-height: 36px;
            padding: 0 14px;
            border: 0;
            border-radius: 999px;
            background: transparent;
            color: var(--secondary);
            font-size: 12px;
            font-weight: 650;
            cursor: pointer;
            transition: background .2s ease, box-shadow .2s ease, transform .2s var(--spring);
        }
        .segment:active, .pill-button:active { transform: scale(.96); }
        .segment.active { background: #fff; color: var(--primary); box-shadow: 0 1px 2px rgba(0, 0, 0, .12), 0 2px 7px rgba(0, 0, 0, .06); }
        .pill-button {
            display: inline-flex;
            min-height: 42px;
            gap: 7px;
            align-items: center;
            padding: 0 16px;
            border: 0;
            border-radius: 999px;
            background: var(--control);
            color: var(--primary);
            font-size: 12px;
            font-weight: 650;
            cursor: pointer;
            transition: transform .2s var(--spring), background .2s ease;
        }
        .pill-button:hover { background: rgba(120, 120, 128, .17); }
        .pill-button.primary { background: var(--blue); color: #fff; }
        .pill-button.primary:hover { background: #0071eb; }
        .pill-button svg { width: 17px; height: 17px; }

        .section { margin-top: 58px; }
        .section.is-hidden, .check-card.is-hidden { display: none; }
        .section-heading { display: flex; align-items: end; justify-content: space-between; gap: 18px; margin: 0 4px 18px; }
        .section-kicker { margin: 0 0 6px; color: var(--blue); font-size: 11px; font-weight: 700; letter-spacing: .09em; text-transform: uppercase; }
        .section-title { margin: 0; font-size: clamp(25px, 3vw, 34px); font-weight: 700; letter-spacing: -.03em; line-height: 1.1; }
        .section-count { flex: 0 0 auto; padding: 7px 11px; border-radius: 999px; background: var(--control); color: var(--tertiary); font-size: 11px; font-weight: 650; }
        .check-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
        .check-card {
            --accent: var(--blue);
            position: relative;
            min-width: 0;
            padding: 24px;
            overflow: hidden;
            border: 1px solid var(--line);
            border-radius: 20px;
            background: var(--surface);
            box-shadow: var(--shadow);
            transition: transform .32s var(--spring), box-shadow .25s ease, border-color .25s ease;
        }
        .check-card:hover { transform: translateY(-3px); border-color: rgba(0, 0, 0, .1); box-shadow: 0 2px 4px rgba(0, 0, 0, .04), 0 14px 34px rgba(0, 0, 0, .08); }
        .check-card.has-table { grid-column: 1 / -1; }
        .check-card.pass { --accent: var(--teal); }
        .check-card.fail { --accent: var(--red); }
        .check-card.info { --accent: var(--blue); }
        .card-top { display: flex; gap: 16px; align-items: flex-start; }
        .status-icon { display: grid; width: 42px; height: 42px; flex: 0 0 42px; place-items: center; border-radius: 13px; background: color-mix(in srgb, var(--accent) 11%, transparent); color: var(--accent); }
        .status-icon svg { width: 21px; height: 21px; }
        .card-copy { min-width: 0; flex: 1; }
        .status-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
        .status-pill { display: inline-flex; align-items: center; gap: 6px; color: var(--accent); font-size: 11px; font-weight: 700; letter-spacing: .025em; }
        .status-pill::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
        .result-count { color: var(--tertiary); font-size: 11px; font-variant-numeric: tabular-nums; }
        .check-title { margin: 11px 0 0; color: var(--primary); font-size: 17px; font-weight: 700; letter-spacing: -.018em; line-height: 1.25; }
        .check-summary { margin: 10px 0 0; color: var(--secondary); font-size: 13px; line-height: 1.55; }

        details { margin-top: 20px; border-top: 1px solid var(--line); }
        details > summary {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            padding: 17px 0 0;
            list-style: none;
            color: var(--blue);
            font-size: 12px;
            font-weight: 650;
            cursor: pointer;
            user-select: none;
        }
        details > summary::-webkit-details-marker { display: none; }
        .chevron { width: 18px; height: 18px; transition: transform .28s var(--spring); }
        details[open] .chevron { transform: rotate(180deg); }
        .table-scroll { margin-top: 14px; overflow-x: auto; border: 1px solid var(--line); border-radius: 14px; }
        table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 12px; white-space: nowrap; }
        th, td { padding: 11px 14px; border: 0; border-bottom: 1px solid var(--line); text-align: left; }
        th { position: sticky; top: 0; background: #f9f9fb; color: var(--tertiary); font-size: 10px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; }
        td { color: var(--secondary); }
        tbody tr:last-child td { border-bottom: 0; }
        tbody tr:hover td { background: rgba(0, 122, 255, .035); }

        .empty-state { display: none; margin: 56px 0; padding: 44px; border: 1px solid var(--line); border-radius: 22px; background: #fff; text-align: center; box-shadow: var(--shadow); }
        .empty-state.visible { display: block; }
        .empty-state-icon { display: grid; width: 52px; height: 52px; margin: 0 auto 15px; place-items: center; border-radius: 17px; background: rgba(0, 122, 255, .1); color: var(--blue); }
        .empty-state h2 { margin: 0; font-size: 20px; letter-spacing: -.02em; }
        .empty-state p { margin: 8px 0 0; color: var(--tertiary); font-size: 13px; }
        .results-note { margin: 20px 4px 0; color: var(--tertiary); font-size: 12px; }
        .footer { display: flex; justify-content: space-between; gap: 20px; margin-top: 72px; padding: 26px 4px 0; border-top: 1px solid rgba(0, 0, 0, .08); color: var(--tertiary); font-size: 11px; }

        .reveal { opacity: 0; transform: translateY(14px); transition: opacity .55s ease, transform .65s var(--spring); }
        .reveal.visible { opacity: 1; transform: translateY(0); }
        :focus-visible { outline: 3px solid rgba(0, 122, 255, .34); outline-offset: 3px; }

        @supports not (color: color-mix(in srgb, red, blue)) {
            .status-icon { background: rgba(120, 120, 128, .1); }
        }
        @media (max-width: 900px) {
            .hero { grid-template-columns: 1fr; gap: 42px; padding: 44px; }
            .score-panel { grid-template-columns: auto 1fr; justify-items: start; }
            .score-ring { width: 174px; height: 174px; }
            .score-number { font-size: 48px; }
            .metrics { grid-template-columns: repeat(2, 1fr); }
            .model-tabs { grid-template-columns: 1fr; }
            .toolbar { align-items: stretch; flex-direction: column; }
            .search-wrap { max-width: none; flex-basis: auto; }
            .toolbar-actions { justify-content: space-between; }
        }
        @media (max-width: 680px) {
            html { scroll-padding-top: 110px; }
            .dock-shell { top: 10px; width: calc(100vw - 20px); }
            .dock { justify-content: flex-start; overflow-x: auto; overflow-y: hidden; border-radius: 18px; scrollbar-width: none; }
            .dock::-webkit-scrollbar { display: none; }
            .dock-tooltip { display: none; }
            .page { width: min(100% - 24px, 1180px); padding-top: 104px; }
            .hero { min-height: 0; padding: 32px 24px; border-radius: 24px; }
            h1 { font-size: clamp(39px, 13vw, 60px); }
            .hero-copy { font-size: 15px; }
            .score-panel { grid-template-columns: 1fr; justify-items: center; }
            .metrics { grid-template-columns: 1fr; }
            .models-panel { padding: 20px; }
            .metric { min-height: 0; }
            .toolbar { top: 78px; margin-bottom: 34px; }
            .toolbar-actions { align-items: stretch; flex-direction: column; }
            .segmented { width: 100%; }
            .segment { flex: 1; padding: 0 10px; }
            .pill-button { justify-content: center; }
            .check-grid { grid-template-columns: 1fr; }
            .check-card.has-table { grid-column: auto; }
            .section { margin-top: 46px; }
            .footer { flex-direction: column; }
        }
        @media (hover: none), (pointer: coarse) {
            .dock-item { transform: none !important; }
            .check-card:hover { transform: none; }
        }
        @media (prefers-reduced-motion: reduce) {
            *, *::before, *::after { scroll-behavior: auto !important; transition-duration: .01ms !important; animation-duration: .01ms !important; animation-iteration-count: 1 !important; }
            .dock-item { transform: none !important; }
            .reveal { opacity: 1; transform: none; }
        }
        @media print {
            @page { margin: 14mm; }
            body { background: #fff; }
            .dock-shell, .toolbar, .pill-button, .empty-state { display: none !important; }
            .page { width: 100%; padding: 0; }
            .hero, .metric, .check-card { box-shadow: none; break-inside: avoid; }
            .hero { min-height: 0; }
            .reveal { opacity: 1; transform: none; }
            .section { break-before: auto; }
            details { break-inside: auto; }
        }
    </style>
""")
    if extra_css:
        parts.append("<style>" + extra_css + "</style>")
    parts.append("""
</head>
<body>
""")

    parts.append('<div class="dock-shell"><nav class="dock" id="dock" aria-label="Secciones del reporte">')
    parts.append('<a class="dock-item active" href="#summary" data-target="summary" aria-label="Resumen">{}<span class="dock-tooltip">Resumen</span></a>'.format(home_icon))
    for index, sec in enumerate(sections):
        icon = section_icons.get(sec, svg_icon('<circle cx="12" cy="12" r="8"></circle><path d="M12 8v4l3 2"></path>'))
        parts.append('<a class="dock-item" href="#model-0-section-{}" data-target="model-0-section-{}" data-section-index="{}" aria-label="{}">{}<span class="dock-tooltip">{}</span></a>'.format(
            index, index, index, html_escape(sec), icon, html_escape(sec)))
    parts.append('</nav></div>')

    parts.append('<main class="page">')
    parts.append('<section class="hero reveal" id="summary">')
    parts.append('<div class="hero-content">')
    parts.append('<p class="eyebrow"><span class="eyebrow-dot"></span>Proyecto · {}</p>'.format(html_escape(project_name)))
    parts.append('<h1><span>{}</span><span class="gradient-title health-title">{}</span></h1>'.format(
        html_escape(resumen.get("titulo", "Reporte de auditoría.")), html_escape(resumen.get("subtitulo", "Salud del modelo."))))
    parts.append('<p class="hero-copy">{}</p>'.format(html_escape(resumen.get("copy", "Una lectura clara del estado del modelo, sus incidencias y los puntos que requieren atención antes de la entrega."))))
    parts.append('<div class="file-meta">')
    parts.append('<div class="file-meta-row">{}<span class="file-path">{}</span></div>'.format(
        svg_icon('<path d="M6 3h8l4 4v14H6z"></path><path d="M14 3v5h5"></path>', 'meta-icon'), html_escape(file_path)))
    parts.append('<div class="file-meta-row">{}<span>{}</span></div>'.format(
        svg_icon('<circle cx="12" cy="12" r="9"></circle><path d="M12 7v5l3 2"></path>', 'meta-icon'), html_escape(report_date)))
    parts.append('</div></div>')
    parts.append('<div class="score-panel">')
    parts.append('<div class="score-ring {}" style="--score: {}" role="img" aria-label="Puntuación de salud: {} por ciento"><div class="score-value"><span class="score-number">{}%</span><span class="score-label">{}</span></div></div>'.format(
        score_class, percent, percent, percent, html_escape(resumen.get("score_label", "SALUD GENERAL"))))
    parts.append('<p class="score-caption">{}</p>'.format(resumen.get("caption") or "{} de {} controles cumplen<br>los criterios evaluados.".format(passed, total)))
    parts.append('</div></section>')

    parts.append('<section class="metrics reveal" aria-label="Resumen de resultados">')
    metricas = resumen.get("metricas") or [("Modelos revisados", model_count, "total"), ("Checks evaluados", total, "total"),
                                           ("Correctos", passed, "pass"), ("Con incidencias", failed, "fail")]
    for etiqueta, valor, clase in metricas:
        parts.append('<article class="metric {}"><div class="metric-label">{}</div><div class="metric-number">{}</div></article>'.format(
            clase, html_escape(etiqueta), html_escape(valor)))
    parts.append('</section>')

    model_icon = svg_icon('<path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z"></path><path d="m4.5 7.8 7.5 4.1 7.5-4.1"></path><path d="M12 12v9"></path>')
    link_model_icon = svg_icon('<path d="M9.5 14.5 14.5 9"></path><path d="M7.2 17.3 5.7 18.8a3.5 3.5 0 0 1-5-5l3-3a3.5 3.5 0 0 1 5 0"></path><path d="m16.8 6.7 1.5-1.5a3.5 3.5 0 0 1 5 5l-3 3a3.5 3.5 0 0 1-5 0"></path>')
    warning_icon = svg_icon('<path d="M12 8v5"></path><path d="M12 17h.01"></path><path d="M10.3 3.8 2.4 17.5A2 2 0 0 0 4.1 20h15.8a2 2 0 0 0 1.7-2.5L13.7 3.8a2 2 0 0 0-3.4 0Z"></path>')
    parts.append('<section class="models-panel reveal" id="models" aria-labelledby="models-title">')
    parts.append('<header class="models-panel-head"><div><h2 class="models-panel-title" id="models-title">Modelos revisados</h2><p class="models-panel-copy">Selecciona un archivo para explorar sus resultados individuales. Cada modelo muestra la revisión de su última sincronización del mes.</p></div><span class="section-count">{} disponibles</span></header>'.format(model_count))
    parts.append('<div class="model-tabs" role="tablist" aria-label="Cambiar modelo">')
    for model_index, report in enumerate(model_reports):
        active_class = " active" if model_index == 0 else ""
        kind_class = "host" if report.get("kind") == "HOST" else "link"
        status_class = "has-failures" if report.get("failed", 0) > 0 else "no-failures"
        kind_label = report.get("kind_label") or ("Modelo activo" if report.get("kind") == "HOST" else "Vínculo Revit")
        current_icon = model_icon if report.get("kind") == "HOST" else link_model_icon
        parts.append('<button class="model-option {} {}{}" type="button" role="tab" aria-selected="{}" aria-controls="model-report-{}" data-model-index="{}">'.format(
            kind_class, status_class, active_class, "true" if model_index == 0 else "false", model_index, model_index))
        parts.append('<span class="model-option-icon">{}</span><span class="model-option-copy"><span class="model-option-kind">{}</span><span class="model-option-name">{}</span><span class="model-option-path">{}</span></span><span class="model-option-score">{}%</span>'.format(
            current_icon, kind_label, html_escape(report.get("name", "Modelo")), html_escape(report.get("path", "")), report.get("percent", 0)))
        parts.append('</button>')
    parts.append('</div>')
    if unavailable_links:
        unavailable_names = ", ".join([x.get("name", "Vínculo") for x in unavailable_links])
        parts.append('<div class="unavailable-note">{}<span><b>{} vínculo(s) sin revisar:</b> {}. Deben estar cargados en Revit para acceder a su contenido.</span></div>'.format(
            warning_icon, len(unavailable_links), html_escape(unavailable_names)))
    parts.append('</section>')

    search_icon = svg_icon('<circle cx="11" cy="11" r="7"></circle><path d="m20 20-4-4"></path>')
    close_icon = svg_icon('<circle cx="12" cy="12" r="9"></circle><path d="m9 9 6 6m0-6-6 6"></path>')
    expand_icon = svg_icon('<path d="m8 3-5 5m0-5v5h5M16 21l5-5m0 5v-5h-5"></path>')
    print_icon = svg_icon('<path d="M7 9V3h10v6"></path><path d="M7 18H5a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"></path><rect x="7" y="14" width="10" height="7" rx="1"></rect>')
    parts.append('<section class="toolbar" aria-label="Herramientas del reporte">')
    parts.append('<label class="search-wrap">{}<span class="sr-only"></span><input class="search-input" id="search" type="search" autocomplete="off" placeholder="Buscar check, sección o resultado…" aria-label="Buscar en el reporte"><button class="clear-search" id="clear-search" type="button" aria-label="Limpiar búsqueda">{}</button></label>'.format(search_icon, close_icon))
    parts.append('<div class="toolbar-actions"><div class="segmented" role="group" aria-label="Filtrar resultados"><button class="segment active" type="button" data-filter="ALL">Todos</button><button class="segment" type="button" data-filter="PASS">Correctos</button><button class="segment" type="button" data-filter="FAIL">Atención</button></div>')
    parts.append('<button class="pill-button" id="toggle-details" type="button">{}<span>Expandir</span></button>'.format(expand_icon))
    if any(rp.get("val_meta") for rp in model_reports):
        hay_val = any(any(r.get("val") or []) for rp in model_reports for r in rp.get("results", []))
        parts.append('<button class="pill-button" id="val-save" type="button"><span>{}</span></button>'.format(
            "Guardar validaciones" if hay_val else "Guardar revisados"))
        if any(any(r.get("val") or []) for rp in model_reports for r in rp.get("results", [])):
            parts.append('<button class="pill-button val-danger" id="val-clear" type="button"><span>Limpiar validaciones</span></button>')
    parts.append('<button class="pill-button primary" id="print-report" type="button">{}<span>Imprimir</span></button></div>'.format(print_icon))
    parts.append('</section>')
    parts.append('<p class="results-note" id="results-note" aria-live="polite"></p>')

    status_icons = {
        "PASS": svg_icon('<path d="m5 12 4 4L19 6"></path>'),
        "FAIL": svg_icon('<path d="M12 8v5"></path><path d="M12 17h.01"></path><path d="M10.3 3.8 2.4 17.5A2 2 0 0 0 4.1 20h15.8a2 2 0 0 0 1.7-2.5L13.7 3.8a2 2 0 0 0-3.4 0Z"></path>'),
        "INFO": svg_icon('<circle cx="12" cy="12" r="9"></circle><path d="M12 11v5"></path><path d="M12 8h.01"></path>')
    }
    status_labels = {"PASS": "Correcto", "FAIL": "Requiere atención", "INFO": "Información"}
    chevron_icon = svg_icon('<path d="m7 10 5 5 5-5"></path>', 'chevron')

    for model_index, report in enumerate(model_reports):
        report_results = report.get("results", [])
        active_class = " active" if model_index == 0 else ""
        val_attr = ""
        if report.get("val_meta"):
            import json as _json
            val_attr = ' data-val="{}"'.format(html_escape(_json.dumps(report["val_meta"], ensure_ascii=False)))
        parts.append('<div class="model-report{}" id="model-report-{}" data-model-index="{}" role="tabpanel"{}>'.format(
            active_class, model_index, model_index, val_attr))
        if report.get("participantes"):
            parts.append(people_panel(report))
        if report.get("extra_html"):
            parts.append(report["extra_html"])
        for index, sec in enumerate(sections):
            section_results = [x for x in report_results if x["section"] == sec]
            if not section_results:
                continue
            parts.append('<section class="section reveal" id="model-{}-section-{}" data-section="{}">'.format(
                model_index, index, html_escape(sec)))
            parts.append('<header class="section-heading"><div><p class="section-kicker">{} · Área de revisión</p><h2 class="section-title">{}</h2></div><span class="section-count">{} checks</span></header>'.format(
                html_escape(report.get("name", "Modelo")), html_escape(sec), len(section_results)))
            parts.append('<div class="check-grid">')
            for r in section_results:
                raw_status = r["status"] if r["status"] in ["PASS", "FAIL", "INFO"] else "INFO"
                css = "pass" if raw_status == "PASS" else "fail" if raw_status == "FAIL" else "info"
                val_card = bool(report.get("val_meta")) and r.get("val_card")
                table_class = " has-table" if (r["rows"] or val_card) else ""
                if val_card and not r["rows"]:
                    table_class += " val-empty"
                search_text = "{} {} {} {} {}".format(report.get("name", ""), sec, r["name"], r["summary"], raw_status).lower()
                marca = bool(report.get("val_meta")) and r.get("key")
                attrs = ' data-key="{}" data-sig="{}"'.format(html_escape(r["key"]), html_escape(r.get("sig", ""))) if marca else ""
                parts.append('<article class="check-card {}{} reveal" data-status="{}" data-search="{}"{}>'.format(
                    css, table_class, raw_status, html_escape(search_text), attrs))
                parts.append('<div class="card-top"><div class="status-icon">{}</div><div class="card-copy">'.format(status_icons.get(raw_status, status_icons["INFO"])))
                n_vis = r.get("visibles", len(r["rows"]))
                conteo = '<span class="result-count">{}</span>'.format("{} resultados".format(n_vis) if n_vis else "Sin incidencias")
                if marca:
                    conteo = '<span class="status-right">{}<label class="rev-mark" title="Marca este recuadro como revisado"><input type="checkbox" class="rev-chk"><span class="rev-switch"></span><span class="rev-text">Revisado</span></label></span>'.format(conteo)
                parts.append('<div class="status-row"><span class="status-pill">{}</span>{}</div>'.format(
                    status_labels.get(raw_status, "Información"), conteo))
                parts.append('<h3 class="check-title">{}</h3>'.format(html_escape(r["name"])))
                parts.append('<p class="check-summary">{}</p>'.format(html_escape(r["summary"])))
                parts.append('</div></div>')
                if r["rows"] or val_card:
                    parts.append('<details><summary><span>Ver {} elementos</span>{}</summary><div class="table-scroll">'.format(r.get("visibles", len(r["rows"])), chevron_icon))
                    if (r.get("val") and any(r["val"])) or val_card:
                        parts.append('<div class="val-bar"><label class="val-check-all"><input type="checkbox" class="val-all"><span>Seleccionar todos</span></label>'
                                     '<span class="val-count" data-n="0">0 seleccionados</span><span class="val-grow"></span>'
                                     '<span class="val-actions-label">Marcar como</span>'
                                     '<button class="val-chip ok" type="button" data-val-bulk="OK"><i></i>OK</button>'
                                     '<button class="val-chip rev" type="button" data-val-bulk="REVIEW"><i></i>Review</button>'
                                     '<button class="val-chip err" type="button" data-val-bulk="ERROR"><i></i>Error</button></div>')
                    parts.append(make_table(r["headers"], r["rows"], r.get("val"), r.get("resaltar"), r.get("resaltar_tono", ""), r.get("diff"), forzar=val_card, cmp=r.get("cmp"),
                                            ref=r.get("ref"), ocultas=r.get("ocultas")))
                    parts.append('</div></details>')
                parts.append('</article>')
            parts.append('</div></section>')
        if report.get("val_meta") and any(x.get("key") for x in report_results):
            # Resumen de checks al final (lo llena el script con el estado "Revisado" de cada recuadro)
            parts.append('<section class="rev-sum" data-rev-sum><header class="section-heading"><div><p class="section-kicker">{} · Resumen</p>'
                         '<h2 class="section-title">Resumen de checks</h2></div><span class="section-count rev-sum-count"></span></header>'
                         '<div class="rev-sum-box"></div></section>'.format(html_escape(report.get("name", "Modelo"))))
        parts.append('</div>')

    parts.append('<div class="empty-state" id="empty-state"><div class="empty-state-icon">{}</div><h2>Sin coincidencias</h2><p>Prueba con otra búsqueda o cambia el filtro seleccionado.</p></div>'.format(search_icon))
    parts.append('<footer class="footer"><span>Model Checker · GCPEASA · 5D_VENTAS</span><span>{}</span></footer>'.format(html_escape(footer_note or ("Generado automáticamente desde las sincronizaciones de Revit · " + report_date))))
    parts.append('</main>')

    parts.append("""<script>
    (function () {
        'use strict';

        var dock = document.getElementById('dock');
        var dockItems = Array.prototype.slice.call(document.querySelectorAll('.dock-item'));
        var sections = Array.prototype.slice.call(document.querySelectorAll('#summary, .section'));
        var cards = Array.prototype.slice.call(document.querySelectorAll('.check-card'));
        var reportSections = Array.prototype.slice.call(document.querySelectorAll('.section'));
        var modelButtons = Array.prototype.slice.call(document.querySelectorAll('.model-option'));
        var modelReports = Array.prototype.slice.call(document.querySelectorAll('.model-report'));
        var searchInput = document.getElementById('search');
        var clearButton = document.getElementById('clear-search');
        var segmentButtons = Array.prototype.slice.call(document.querySelectorAll('.segment'));
        var resultNote = document.getElementById('results-note');
        var emptyState = document.getElementById('empty-state');
        var toggleDetails = document.getElementById('toggle-details');
        var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        var finePointer = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
        var activeFilter = 'ALL';
        var activeModelIndex = 0;
        var detailsExpanded = false;

        function normalize(value) {
            return (value || '').toLocaleLowerCase('es').normalize ?
                (value || '').toLocaleLowerCase('es').normalize('NFD').replace(/[\u0300-\u036f]/g, '') :
                (value || '').toLocaleLowerCase('es');
        }

        function applyFilters() {
            var query = normalize(searchInput.value.trim());
            var visibleCount = 0;
            var activeReport = document.querySelector('.model-report.active');
            var activeCards = activeReport ? Array.prototype.slice.call(activeReport.querySelectorAll('.check-card')) : [];
            var activeSections = activeReport ? Array.prototype.slice.call(activeReport.querySelectorAll('.section')) : [];

            activeCards.forEach(function (card) {
                var matchesFilter = activeFilter === 'ALL' || card.getAttribute('data-status') === activeFilter;
                var matchesSearch = !query || normalize(card.getAttribute('data-search')).indexOf(query) !== -1;
                var visible = matchesFilter && matchesSearch;
                card.classList.toggle('is-hidden', !visible);
                if (visible) visibleCount += 1;
            });

            activeSections.forEach(function (section) {
                var sectionCards = Array.prototype.slice.call(section.querySelectorAll('.check-card'));
                var sectionVisible = sectionCards.some(function (card) { return !card.classList.contains('is-hidden'); });
                section.classList.toggle('is-hidden', !sectionVisible);
                var visibleInSection = sectionCards.filter(function (card) { return !card.classList.contains('is-hidden'); }).length;
                var counter = section.querySelector('.section-count');
                if (counter) counter.textContent = visibleInSection + (visibleInSection === 1 ? ' check' : ' checks');
            });

            clearButton.classList.toggle('visible', searchInput.value.length > 0);
            emptyState.classList.toggle('visible', visibleCount === 0);
            resultNote.textContent = visibleCount + (visibleCount === 1 ? ' resultado visible' : ' resultados visibles');
        }

        function selectModel(modelIndex) {
            activeModelIndex = modelIndex;
            modelReports.forEach(function (report) {
                var isActive = parseInt(report.getAttribute('data-model-index'), 10) === modelIndex;
                report.classList.toggle('active', isActive);
                if (isActive) {
                    Array.prototype.slice.call(report.querySelectorAll('.reveal')).forEach(function (element) {
                        element.classList.add('visible');
                    });
                }
            });
            modelButtons.forEach(function (button) {
                var isActive = parseInt(button.getAttribute('data-model-index'), 10) === modelIndex;
                button.classList.toggle('active', isActive);
                button.setAttribute('aria-selected', isActive ? 'true' : 'false');
            });
            dockItems.forEach(function (item) {
                var sectionIndex = item.getAttribute('data-section-index');
                if (sectionIndex !== null) {
                    var target = 'model-' + modelIndex + '-section-' + sectionIndex;
                    item.setAttribute('data-target', target);
                    item.setAttribute('href', '#' + target);
                }
            });
            applyFilters();
        }

        modelButtons.forEach(function (button) {
            button.addEventListener('click', function () {
                selectModel(parseInt(button.getAttribute('data-model-index'), 10));
            });
        });

        searchInput.addEventListener('input', applyFilters);
        searchInput.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') {
                searchInput.value = '';
                applyFilters();
            }
        });
        clearButton.addEventListener('click', function () {
            searchInput.value = '';
            searchInput.focus();
            applyFilters();
        });

        segmentButtons.forEach(function (button) {
            button.addEventListener('click', function () {
                activeFilter = button.getAttribute('data-filter');
                segmentButtons.forEach(function (item) { item.classList.toggle('active', item === button); });
                applyFilters();
            });
        });

        toggleDetails.addEventListener('click', function () {
            detailsExpanded = !detailsExpanded;
            Array.prototype.slice.call(document.querySelectorAll('details')).forEach(function (detail) {
                detail.open = detailsExpanded;
            });
            toggleDetails.querySelector('span').textContent = detailsExpanded ? 'Contraer' : 'Expandir';
        });
        document.getElementById('print-report').addEventListener('click', function () { window.print(); });

        if (finePointer && !reduceMotion) {
            dock.addEventListener('mousemove', function (event) {
                dockItems.forEach(function (item) {
                    var rect = item.getBoundingClientRect();
                    var center = rect.left + rect.width / 2;
                    var distance = Math.abs(event.clientX - center);
                    var scale = Math.max(1, 1.38 - distance / 150);
                    item.style.transform = 'scale(' + scale.toFixed(3) + ')';
                });
            });
            dock.addEventListener('mouseleave', function () {
                dockItems.forEach(function (item) { item.style.transform = ''; });
            });
        }

        if ('IntersectionObserver' in window) {
            var revealObserver = new IntersectionObserver(function (entries) {
                entries.forEach(function (entry) {
                    if (entry.isIntersecting) {
                        entry.target.classList.add('visible');
                        revealObserver.unobserve(entry.target);
                    }
                });
            }, { threshold: .08 });
            Array.prototype.slice.call(document.querySelectorAll('.reveal')).forEach(function (element) {
                revealObserver.observe(element);
            });

            var activeObserver = new IntersectionObserver(function (entries) {
                entries.forEach(function (entry) {
                    if (entry.isIntersecting) {
                        dockItems.forEach(function (item) {
                            item.classList.toggle('active', item.getAttribute('data-target') === entry.target.id);
                        });
                    }
                });
            }, { rootMargin: '-18% 0px -68% 0px', threshold: 0 });
            sections.forEach(function (section) { activeObserver.observe(section); });
        } else {
            Array.prototype.slice.call(document.querySelectorAll('.reveal')).forEach(function (element) {
                element.classList.add('visible');
            });
        }

        applyFilters();
    }());
    </script>
""")
    if extra_script:
        parts.append("<script>" + extra_script + "</script>")
    parts.append("""
</body>
</html>""")
    return "".join(parts)


def people_panel(report):
    """Responsable (quien mas sincronizo el modelo en el mes) y los demas participantes."""
    filas = []
    for p in report.get("participantes", []):
        rol = "Responsable" if p.get("integrante") == report.get("responsable") else "Participante"
        filas.append([p.get("integrante", ""), p.get("equipo", ""), rol, p.get("syncs", 0), p.get("ultima", "")])
    resp = report.get("responsable") or "Sin responsable del listado"
    return ('<section class="models-panel reveal visible" style="margin:0 0 8px">'
            '<header class="models-panel-head" style="margin-bottom:12px"><div>'
            '<h2 class="models-panel-title">Responsable · {}</h2>'
            '<p class="models-panel-copy">Integrante del listado con más sincronizaciones del modelo en el mes. '
            'Revisión de la última sincronización: {}.</p></div>'
            '<span class="section-count">{} sincronizaciones</span></header>'
            '<div class="table-scroll" style="margin-top:0">{}</div></section>').format(
                html_escape(resp), html_escape(report.get("fecha_auditoria", "")),
                sum(int(p.get("syncs", 0)) for p in report.get("participantes", [])),
                make_table(["Integrante", "Equipo", "Rol", "Sincronizaciones", "Última sincronización"], filas))
