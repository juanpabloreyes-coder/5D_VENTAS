"""Validacion manual de "Base de Datos vs Revit" (la misma idea del boton de pyRevit, ahora en el reporte).

Se pueden cambiar de estatus (OK / Review / Error):
  - los conceptos REVIEW de origen (codigo especial 1111111111), y
  - los conceptos SIN Control (parametro Control vacio): tecnica para no mostrar conceptos que no son
    necesarios pero que aparecen solos por ser inherentes a otros elementos.

Las decisiones se guardan en la carpeta compartida, un archivo por modelo:
    03374_5D_VENTAS\\validaciones\\urn_<linaje>.json
    {"version": 1, "item_id": "...", "modelo": "...", "actualizado": "...",
     "decisiones": {"<huella>": {"estado": "OK", "fecha": "..."}}}
El reporte las aplica al % oficial en la siguiente corrida. La huella junta ID, alcance, concepto, tipo,
codigo, descripcion, unidad, partida y control (igual que el boton de pyRevit): si cualquiera cambia en Revit,
la validacion ya no aplica y el concepto se vuelve a revisar."""
import html
import json
import logging
from pathlib import Path

log = logging.getLogger("cat5d_sync.validacion5d")
ESTADOS = ("OK", "REVIEW", "ERROR")
MOTIVO_MANUAL = {"OK": "Validado manualmente como OK", "ERROR": "Marcado manualmente como Error",
                 "REVIEW": "Pendiente de revisión visual"}

# filas del add-in: 0 ID, 1 categoria, 2 tipo, 3 alcance, 4 concepto, 5 control, 6 codigo, 7 descripcion,
# 8 unidad, 9 partida, 10 estado, 11 motivo, 12 campos en blanco, 13 residuo aislado


def _t(v):
    return "" if v is None else str(v).strip()


def huella(f):
    return "|".join(_t(f[i]) for i in (0, 3, 4, 2, 6, 7, 8, 9, 5))


def sin_control(f):
    return _t(f[5]) == ""


def elegible(f):
    return _t(f[10]) == "REVIEW" or sin_control(f)


def archivo(carpeta_5d, item_id):
    lin = str(item_id or "").split(":")[-1]
    return Path(carpeta_5d) / "validaciones" / f"urn_{lin}.json"


def leer(carpeta_5d, item_id):
    if not carpeta_5d:
        return {}
    p = archivo(carpeta_5d, item_id)
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8-sig"))
        return {h: v for h, v in (d.get("decisiones") or {}).items()
                if isinstance(v, dict) and v.get("estado") in ESTADOS}
    except Exception as e:
        log.warning("No se pudo leer %s: %s", p, e)
        return {}


PREFIJO_DESCARGA = "5D_validacion__"


def recoger_descargas(carpeta_5d, descargas):
    """Mueve a 03374_5D_VENTAS\\validaciones los archivos que descargo "Guardar validaciones"
    (Descargas\\5D_validacion__urn_<linaje>*.json). Se aplican en orden de fecha y se combinan con lo
    guardado: lo validado se agrega/actualiza, lo regresado a su origen se quita. -> lista de modelos."""
    descargas = Path(descargas)
    if not carpeta_5d or not descargas.is_dir():
        return []
    lote = []
    for f in descargas.glob(PREFIJO_DESCARGA + "urn_*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8-sig"))
            if d.get("item_id"):
                lote.append((d.get("actualizado") or "", f, d))
        except Exception as e:
            log.warning("No se pudo leer %s: %s", f, e)
    hechos = []
    for _, f, d in sorted(lote, key=lambda x: x[0]):
        destino = archivo(carpeta_5d, d["item_id"])
        try:
            actual = json.loads(destino.read_text(encoding="utf-8-sig")) if destino.exists() else {}
        except Exception:
            actual = {}
        dec = dict(actual.get("decisiones") or {})
        rev = dict(actual.get("revisados") or {})
        dec.update(d.get("decisiones") or {})
        for h in d.get("quitar") or []:
            dec.pop(h, None)
        rev.update(d.get("revisados") or {})
        for k in d.get("quitar_revisados") or []:
            rev.pop(k, None)
        nuevo = {"version": 1, "item_id": d["item_id"], "modelo": d.get("modelo") or actual.get("modelo", ""),
                 "actualizado": d.get("actualizado", ""), "decisiones": dec, "revisados": rev}
        destino.parent.mkdir(parents=True, exist_ok=True)
        tmp = destino.with_suffix(".tmp")
        tmp.write_text(json.dumps(nuevo, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(destino)
        try:
            f.unlink()
        except Exception:
            pass
        hechos.append(nuevo["modelo"] or d["item_id"])
    return hechos


def leer_revisados(carpeta_5d, item_id):
    """Recuadros marcados como "Revisado": {"<seccion>|<recuadro>": {"firma": "...", "fecha": "..."}}"""
    if not carpeta_5d:
        return {}
    p = archivo(carpeta_5d, item_id)
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8-sig"))
        return {k: v for k, v in (d.get("revisados") or {}).items() if isinstance(v, dict)}
    except Exception:
        return {}


def firma(contenido):
    """Firma del contenido de un recuadro: si cambia (otros conceptos, otros datos), la marca de Revisado
    deja de aplicar."""
    import hashlib
    return hashlib.sha1(json.dumps(contenido, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def aplicar(filas, decisiones):
    """-> (filas con estatus validados, vals, aplicadas, ignoradas)
    vals: lista paralela a filas; None si el concepto no se puede validar, o {h, o (estatus de origen),
    e (estatus actual), rev (Review de origen), sc (sin Control)}."""
    nuevas, vals, usadas = [], [], set()
    for f in filas:
        f = list(f)
        v = None
        if elegible(f):
            h = huella(f)
            origen = _t(f[10]) or "ERROR"
            filas_m0 = f[11]  # motivo de origen
            dec = decisiones.get(h)
            if dec:
                usadas.add(h)
                if dec["estado"] != origen:
                    f[10] = dec["estado"]
                    f[11] = MOTIVO_MANUAL[dec["estado"]] + f" (antes: {origen})"
            v = {"h": h, "o": origen, "e": f[10], "rev": origen == "REVIEW", "sc": sin_control(f), "m0": _t(filas_m0)}
        nuevas.append(f)
        vals.append(v)
    ignoradas = len(set(decisiones) - usadas)
    return nuevas, vals, len(usadas), ignoradas


def aplicar_diferencias(filas, tipo, decisiones, hoja_i=0, fila_i=1, col_i=2, a_i=4, b_i=5):
    """Exportado vs Revit: cada diferencia de celda se puede validar (OK / Review / Error; de origen Error).
    Una fila cuenta como igual cuando TODAS sus diferencias quedan validadas como OK.
    -> (vals paralela a filas, filas_validadas_ok, usadas)"""
    vals, grupos, usadas = [], {}, set()
    for f in filas:
        if not _t(f[col_i]):          # tabla agregada/eliminada: no se valida
            vals.append(None)
            continue
        h = "|".join(["exp", tipo, _t(f[hoja_i]), _t(f[fila_i]), _t(f[col_i]), _t(f[a_i]), _t(f[b_i])])
        dec = decisiones.get(h)
        if dec:
            usadas.add(h)
        e = dec["estado"] if dec else "ERROR"
        g = f"{tipo}|{_t(f[hoja_i])}|{_t(f[fila_i])}"
        grupos.setdefault(g, []).append(e)
        vals.append({"h": h, "o": "ERROR", "e": e, "g": g, "k": tipo, "rev": False, "sc": False})
    ok = sum(1 for es in grupos.values() if all(x == "OK" for x in es))
    return vals, ok, usadas


def conteos(filas):
    c = {"OK": 0, "REVIEW": 0, "ERROR": 0}
    for f in filas:
        e = _t(f[10])
        c[e if e in c else "ERROR"] += 1
    return c


# ---------------------------------------------------------------- pagina
ESTILO = """
/* ===== Validacion 5D: controles con el lenguaje del reporte (fresco, ligero, con movimiento) ===== */
:root{--ok:#30b0c7;--ok-ink:#127e93;--rev:#ff9f0a;--rev-ink:#b86e00;--err:#ff453a;--err-ink:#d70015;--sel:#007aff}

/* casillas: circulares, con check animado y halo */
.val-sel,.val-all{appearance:none;-webkit-appearance:none;flex:0 0 auto;width:20px;height:20px;margin:0;border-radius:50%;
  border:1.5px solid rgba(60,60,67,.22);background:var(--surface);cursor:pointer;display:inline-grid;place-content:center;position:relative;
  transition:background .2s ease,border-color .2s ease,box-shadow .25s ease,transform .25s var(--spring)}
.val-sel::after,.val-all::after{content:"";width:11px;height:11px;transform:scale(0) rotate(-20deg);transition:transform .28s var(--spring);
  background:no-repeat center/11px url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 12'%3E%3Cpath d='M2.4 6.3 4.9 8.8 9.7 3.4' fill='none' stroke='white' stroke-width='2.1' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E")}
.val-sel:hover,.val-all:hover{border-color:var(--sel);box-shadow:0 0 0 5px rgba(0,122,255,.1)}
.val-sel:checked,.val-all:checked{background:linear-gradient(135deg,#2b8cff,#0060df);border-color:transparent;box-shadow:0 2px 8px rgba(0,122,255,.35)}
.val-sel:checked::after,.val-all:checked::after{transform:scale(1) rotate(0)}
.val-sel:active,.val-all:active{transform:scale(.85)}
.val-sel:focus-visible,.val-all:focus-visible,.seg3 button:focus-visible,.rev-chk:focus-visible+.rev-switch{outline:none;box-shadow:0 0 0 4px rgba(0,122,255,.25)}

/* estatus: control segmentado con indicador que se desliza */
.val-st{position:absolute;opacity:0;pointer-events:none;width:1px;height:1px}
.val-cell{display:flex;flex-direction:column;align-items:flex-start;gap:6px;position:relative}
.seg3{--i:0;position:relative;display:inline-grid;grid-template-columns:repeat(3,62px);padding:3px;border-radius:999px;background:rgba(120,120,128,.1);isolation:isolate}
.seg3::before{content:"";position:absolute;z-index:-1;top:3px;bottom:3px;left:3px;width:calc((100% - 6px)/3);border-radius:999px;
  transform:translateX(calc(var(--i) * 100%));transition:transform .35s var(--spring),background .25s ease,box-shadow .25s ease;
  background:var(--ok);box-shadow:0 2px 8px rgba(48,176,199,.4)}
.seg3[data-e="REVIEW"]{--i:1}.seg3[data-e="ERROR"]{--i:2}
.seg3[data-e="REVIEW"]::before{background:var(--rev);box-shadow:0 2px 8px rgba(255,159,10,.4)}
.seg3[data-e="ERROR"]::before{background:var(--err);box-shadow:0 2px 8px rgba(255,69,58,.4)}
.seg3 button{border:0;background:none;font:inherit;font-size:11px;font-weight:700;letter-spacing:.01em;padding:5px 0;text-align:center;border-radius:999px;
  color:var(--tertiary);cursor:pointer;white-space:nowrap;transition:color .25s ease}
.seg3 button:hover{color:var(--primary)}
.seg3 button.on{color:#fff}
.val-tags{display:flex;gap:4px;flex-wrap:wrap}
.val-tag{display:inline-flex;align-items:center;gap:4px;font-size:10px;font-weight:600;padding:2px 8px;border-radius:999px;background:rgba(120,120,128,.1);color:var(--secondary);white-space:nowrap}
.val-tag::before{content:"";width:5px;height:5px;border-radius:50%;background:currentColor;opacity:.6}

/* filas */
tr.val-row td{transition:background .25s ease}
tr.val-row:hover td{background:rgba(0,122,255,.035)}
tr.val-row.val-sel-on td{background:rgba(0,122,255,.07)}
tr.val-cambiado td:first-child{box-shadow:inset 3px 0 0 var(--sel)}
tr.val-cambiado td{background:rgba(0,122,255,.05)}
@keyframes valPulse{0%{box-shadow:inset 0 0 0 999px rgba(0,122,255,.14)}100%{box-shadow:inset 0 0 0 999px rgba(0,122,255,0)}}
tr.val-pulse td{animation:valPulse .7s ease-out}

/* barra de seleccion por recuadro: flotante, vidrio */
.val-bar{position:relative;display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:12px 0 8px;padding:8px 10px 8px 12px;border-radius:16px;
  background:rgba(255,255,255,.72);backdrop-filter:saturate(180%) blur(14px);-webkit-backdrop-filter:saturate(180%) blur(14px);
  box-shadow:0 0 0 1px rgba(0,0,0,.05),0 6px 20px rgba(0,0,0,.06)}
.val-check-all{display:flex;gap:9px;align-items:center;font-size:12px;font-weight:600;color:var(--secondary);cursor:pointer}
.val-count{font-size:11px;font-weight:700;color:var(--tertiary);padding:3px 9px;border-radius:999px;background:rgba(120,120,128,.08);transition:all .25s var(--spring)}
.val-count[data-n]:not([data-n="0"]){color:#fff;background:var(--sel);transform:scale(1.04)}
.val-grow{flex:1}
.val-actions-label{font-size:11px;font-weight:600;color:var(--tertiary);margin-right:2px}
.val-chip{display:inline-flex;align-items:center;gap:6px;border:0;font:inherit;font-size:12px;font-weight:700;padding:7px 13px;border-radius:999px;cursor:pointer;
  transition:transform .2s var(--spring),box-shadow .2s ease,background .2s ease}
.val-chip i{width:8px;height:8px;border-radius:50%;background:currentColor}
.val-chip.ok{background:rgba(48,176,199,.12);color:var(--ok-ink)}
.val-chip.rev{background:rgba(255,159,10,.14);color:var(--rev-ink)}
.val-chip.err{background:rgba(255,69,58,.11);color:var(--err-ink)}
.val-chip:hover{transform:translateY(-1px);box-shadow:0 4px 12px rgba(0,0,0,.08)}
.val-chip:active{transform:scale(.94)}
#val-clear{color:var(--err-ink)}
.pill-button.val-pendiente{background:linear-gradient(135deg,#2b8cff,#0060df);color:#fff;box-shadow:0 4px 14px rgba(0,122,255,.35)}

/* lo que explica el problema */
th.hl,th.dxcol{color:var(--err-ink)}
th.hl::after,th.dxcol::after{content:"";display:inline-block;width:6px;height:6px;margin-left:6px;border-radius:50%;background:var(--err);vertical-align:middle;box-shadow:0 0 0 3px rgba(255,69,58,.15)}
th.hl.hl-rev{color:var(--rev-ink)}th.hl.hl-rev::after{background:var(--rev);box-shadow:0 0 0 3px rgba(255,159,10,.18)}
.hl-chip{display:inline-block;padding:2px 9px;border-radius:8px;font-weight:600;color:var(--err-ink);
  background:linear-gradient(180deg,rgba(255,69,58,.09),rgba(255,69,58,.14));box-shadow:inset 0 0 0 1px rgba(255,69,58,.18)}
td.hl-rev .hl-chip{color:var(--rev-ink);background:linear-gradient(180deg,rgba(255,159,10,.1),rgba(255,159,10,.16));box-shadow:inset 0 0 0 1px rgba(255,159,10,.25)}
tr.val-cambiado .hl-chip{color:var(--secondary);background:rgba(120,120,128,.08);box-shadow:none}
mark.dx{color:var(--err-ink);font-weight:700;background:linear-gradient(180deg,transparent 55%,rgba(255,69,58,.28) 55%);border-radius:2px;padding:0 1px;
  text-decoration:underline wavy rgba(255,69,58,.55);text-decoration-thickness:1px;text-underline-offset:3px;box-decoration-break:clone;-webkit-box-decoration-break:clone}
td.dxcell{font-variant-numeric:tabular-nums}
/* Revit contra Base de Datos en el mismo campo */
.cmp{display:flex;flex-direction:column;gap:4px}
.cmp span{display:block;line-height:1.35}
.cmp em{display:inline-block;min-width:74px;text-align:center;margin-right:8px;font-style:normal;font-size:9px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;
  color:var(--tertiary);padding:1px 6px;border-radius:6px;background:rgba(120,120,128,.1);text-align:center}
.cmp-c{color:var(--tertiary)}
.cmp-c em{background:rgba(48,176,199,.14);color:var(--ok-ink)}
.cmp-c mark.dx{color:var(--ok-ink);background:linear-gradient(180deg,transparent 55%,rgba(48,176,199,.3) 55%);text-decoration-color:rgba(48,176,199,.6)}

/* "Revisado": interruptor */
.status-right{display:flex;align-items:center;gap:10px}
.rev-mark{display:inline-flex;align-items:center;gap:8px;font-size:11px;font-weight:700;letter-spacing:.02em;color:var(--tertiary);cursor:pointer;user-select:none;white-space:nowrap}
.rev-chk{position:absolute;opacity:0;width:1px;height:1px}
.rev-switch{position:relative;width:34px;height:20px;border-radius:999px;background:rgba(120,120,128,.2);transition:background .25s ease}
.rev-switch::after{content:"";position:absolute;top:2px;left:2px;width:16px;height:16px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.2);transition:transform .3s var(--spring)}
.rev-mark:hover .rev-switch{background:rgba(120,120,128,.3)}
.rev-chk:checked+.rev-switch{background:#34c759}
.rev-chk:checked+.rev-switch::after{transform:translateX(14px)}
.check-card.revisado .rev-mark{color:#248a3d}
.check-card.revisado{box-shadow:0 0 0 2px rgba(52,199,89,.45),0 10px 30px rgba(52,199,89,.12)}
.check-card.revisado .status-icon{transition:transform .3s var(--spring)}
.rev-cambio{font-size:10px;font-weight:700;color:var(--rev-ink);padding:2px 8px;border-radius:999px;background:rgba(255,159,10,.14);white-space:nowrap}
.check-card.val-empty{display:none!important}
.results-note.val-unsaved{color:var(--rev-ink);font-weight:600}
@media print{.val-bar,.val-sel,#val-save,#val-clear,.rev-switch{display:none}.seg3 button:not(.on){display:none}.seg3::before{display:none}.seg3 button.on{color:var(--primary)}}
/* resumen de checks al final del modelo */
.rev-sum{margin-top:58px}
.rev-sum-box{background:var(--surface);border:1px solid var(--line);border-radius:24px;box-shadow:var(--shadow);padding:22px 24px}
.rs-head{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.rs-big{font-size:30px;font-weight:700;letter-spacing:-.03em}
.rs-big small{font-size:15px;color:var(--tertiary);font-weight:600;margin-left:4px}
.rs-msg{font-size:14px;font-weight:600;padding:6px 12px;border-radius:999px;background:rgba(255,159,10,.12);color:var(--rev-ink)}
.rs-msg.done{background:rgba(52,199,89,.14);color:#248a3d}
.rs-bar{flex:1 1 220px;height:8px;border-radius:99px;background:var(--control);overflow:hidden}
.rs-bar i{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,#34c759,#30d158);transition:width .5s var(--spring)}
.rs-grp{margin-top:20px}
.rs-grp h4{margin:0 0 6px;font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:var(--blue)}
.rs-row{display:grid;grid-template-columns:22px 1fr auto auto;align-items:center;gap:12px;width:100%;text-align:left;font:inherit;color:inherit;
  background:none;border:0;border-top:1px solid var(--line);padding:10px 6px;cursor:pointer;border-radius:10px;transition:background .15s ease}
.rs-row:hover{background:rgba(0,122,255,.06)}
.rs-dot{width:18px;height:18px;border-radius:50%;border:1.5px dashed rgba(60,60,67,.35);display:grid;place-content:center}
.rs-row.ok .rs-dot{border:0;background:#34c759}
.rs-row.ok .rs-dot::after{content:"";width:10px;height:10px;background:no-repeat center/10px url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 12'%3E%3Cpath d='M2.4 6.3 4.9 8.8 9.7 3.4' fill='none' stroke='white' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E")}
.rs-name{font-weight:600;font-size:14px}
.rs-name em{display:block;font-style:normal;font-weight:500;font-size:12px;color:var(--tertiary)}
.rs-st{font-size:11px;font-weight:700;padding:3px 9px;border-radius:999px;background:var(--control);color:var(--secondary)}
.rs-st.FAIL{background:rgba(255,59,48,.12);color:var(--err-ink)}.rs-st.PASS{background:rgba(48,176,199,.14);color:var(--ok-ink)}
.rs-rev{font-size:12px;font-weight:700;min-width:96px;text-align:right;color:var(--rev-ink)}
.rs-row.ok .rs-rev{color:#248a3d}.rs-row.cambio .rs-rev{color:var(--err-ink)}
@keyframes revFlash{0%,100%{box-shadow:var(--shadow)}30%{box-shadow:0 0 0 4px rgba(0,122,255,.45),0 12px 34px rgba(0,122,255,.2)}}
.check-card.rev-flash{animation:revFlash 1.4s ease 2}
@media (max-width:640px){.rs-row{grid-template-columns:22px 1fr auto}.rs-st{display:none}}
.check-card details .table-scroll{overflow:auto}
"""

SCRIPT = r"""
(function () {
  var reports = Array.prototype.slice.call(document.querySelectorAll('.model-report[data-val]'));
  if (!reports.length) return;
  var nota = document.getElementById('results-note');
  var PREFIJO = '5D_validacion__';
  var MOT = {OK: 'Validado manualmente como OK', ERROR: 'Marcado manualmente como Error', REVIEW: 'Pendiente de revisión visual'};
  function filas(rep) { return Array.prototype.slice.call(rep.querySelectorAll('tr.val-row')); }
  function pintar(tr) {
    var e = tr.querySelector('.val-st').value, o = tr.getAttribute('data-o');
    tr.classList.remove('st-OK', 'st-REVIEW', 'st-ERROR'); tr.classList.add('st-' + e);
    tr.classList.toggle('val-cambiado', e !== o);
    var seg = tr.querySelector('.seg3');
    if (seg) {
      seg.setAttribute('data-e', e);
      Array.prototype.forEach.call(seg.children, function (b) { b.classList.toggle('on', b.getAttribute('data-e') === e); });
    }
    ubicar(tr, e);
    capturas(tr, e);
  }
  // Recuadros de captura (campos en blanco / residuos): un concepto validado como OK deja de mostrarse ahi
  function capturas(tr, e) {
    var rep = tr.closest('.model-report'), h = tr.getAttribute('data-h'); if (!rep || !h) return;
    var ocultar = e === 'OK' && tr.getAttribute('data-o') !== 'OK';
    var cards = [];
    Array.prototype.forEach.call(rep.querySelectorAll('tr[data-ref]'), function (r) {
      if (r.getAttribute('data-ref') !== h) return;
      var antes = r.style.display === 'none';
      if (antes === ocultar) return;
      r.style.display = ocultar ? 'none' : '';
      var c = r.closest('.check-card'); if (c && cards.indexOf(c) < 0) cards.push(c);
    });
    cards.forEach(function (card) {
      var n = 0;
      Array.prototype.forEach.call(card.querySelectorAll('table tr'), function (r, i) { if (i > 0 && r.style.display !== 'none') n++; });
      var rc = card.querySelector('.result-count'); if (rc) rc.textContent = n ? n + ' resultados' : 'Sin incidencias';
      var sm = card.querySelector('details summary span'); if (sm) sm.textContent = 'Ver ' + n + ' elementos';
      var cs = card.querySelector('.check-summary'); if (cs) cs.textContent = cs.textContent.replace(/\d+/, String(n));
    });
  }
  // Mueve el concepto al recuadro que le toca segun su estatus actual
  var DESTINO = {OK: 'COINCIDEN CON CATÁLOGO', REVIEW: 'REVISIÓN MANUAL (CÓDIGO 1111111111)'};
  function cardDe(rep, key) {
    var cs = rep.querySelectorAll('.check-card[data-key]');
    for (var i = 0; i < cs.length; i++) if (cs[i].getAttribute('data-key') === key) return cs[i];
    return null;
  }
  function actualizarCard(card) {
    if (!card) return;
    var tabla = card.querySelector('table'); if (!tabla) return;
    var n = tabla.querySelectorAll('tr').length - 1;
    var rc = card.querySelector('.result-count'); if (rc) rc.textContent = n ? n + ' resultados' : 'Sin incidencias';
    var sm = card.querySelector('details summary span'); if (sm) sm.textContent = 'Ver ' + n + ' elementos';
    var cs = card.querySelector('.check-summary');
    if (cs) cs.textContent = cs.textContent.replace(/^\d+/, String(n));
    card.classList.toggle('val-empty', n === 0);
    contarSel(card);
  }
  function ubicar(tr, e) {
    var sec = tr.getAttribute('data-sec'); if (!sec) return;
    var rep = tr.closest('.model-report'); if (!rep) return;
    var key = DESTINO[e] ? sec + '|' + DESTINO[e] : tr.getAttribute('data-home');
    var destino = cardDe(rep, key), origen = tr.closest('.check-card');
    if (!destino || destino === origen) return;
    var tabla = destino.querySelector('table'); if (!tabla) return;
    var cuerpo = tabla.tBodies[0] || tabla, cab = cuerpo.querySelector('tr');
    var chk = tr.querySelector('.val-sel'); if (chk) chk.checked = false;
    cuerpo.insertBefore(tr, cab ? cab.nextSibling : null);
    actualizarCard(origen); actualizarCard(destino);
    var det = destino.querySelector('details'); if (det && origen && origen.querySelector('details') && origen.querySelector('details').open) det.open = true;
  }
  function segmento(tr) {
    var sel = tr.querySelector('.val-st'); if (!sel || tr.querySelector('.seg3')) return;
    var seg = document.createElement('div'); seg.className = 'seg3'; seg.setAttribute('role', 'radiogroup');
    [['OK', 'OK'], ['REVIEW', 'Review'], ['ERROR', 'Error']].forEach(function (x) {
      var b = document.createElement('button'); b.type = 'button'; b.setAttribute('data-e', x[0]); b.textContent = x[1];
      b.addEventListener('click', function () {
        if (sel.value === x[0]) return;
        sel.value = x[0]; sel.dispatchEvent(new Event('change'));
        tr.classList.remove('val-pulse'); void tr.offsetWidth; tr.classList.add('val-pulse');
      });
      seg.appendChild(b);
    });
    sel.parentNode.insertBefore(seg, sel);
  }
  function contarSel(card) {
    var n = card.querySelectorAll('.val-sel:checked').length, c = card.querySelector('.val-count');
    if (c) { c.setAttribute('data-n', n); c.textContent = n + (n === 1 ? ' seleccionado' : ' seleccionados'); }
    Array.prototype.forEach.call(card.querySelectorAll('tr.val-row'), function (tr) {
      tr.classList.toggle('val-sel-on', tr.querySelector('.val-sel').checked);
    });
  }
  // Exportado vs Revit: una fila cuenta como igual cuando todas sus diferencias estan validadas como OK
  function pctExp(rep) {
    var meta = JSON.parse(rep.getAttribute('data-val')), g = {};
    filas(rep).forEach(function (tr) {
      var k = tr.getAttribute('data-g'); if (!k) return;
      g[k] = (g[k] === undefined ? true : g[k]) && tr.querySelector('.val-st').value === 'OK';
    });
    var okI = 0, okV = 0;
    Object.keys(g).forEach(function (k) { if (g[k]) { if (k.indexOf('int|') === 0) okI++; else okV++; } });
    var c = {it: meta.int.total, ii: meta.int.raw + okI, vt: meta.vig.total, vi: meta.vig.raw + okV};
    var p = Math.round(((c.it ? 100 * c.ii / c.it : 100) + (c.vt ? 100 * c.vi / c.vt : 100)) / 2);
    var tab = document.querySelector('.model-option[data-model-index="' + rep.getAttribute('data-model-index') + '"] .model-option-score');
    if (tab) tab.textContent = p + '%';
    rep._c = c;
    generalExp();
  }
  function generalExp() {
    var t = {it: 0, ii: 0, vt: 0, vi: 0};
    reports.forEach(function (r) {
      var c = r._c; if (!c) { var m = JSON.parse(r.getAttribute('data-val')); c = {it: m.int.total, ii: m.int.iguales, vt: m.vig.total, vi: m.vig.iguales}; }
      t.it += c.it; t.ii += c.ii; t.vt += c.vt; t.vi += c.vi;
    });
    var p = t.it ? Math.round(100 * t.ii / t.it) : 100, pv = t.vt ? Math.round(100 * t.vi / t.vt) : 100;
    var pg = Math.round(((t.it ? 100 * t.ii / t.it : 100) + (t.vt ? 100 * t.vi / t.vt : 100)) / 2);
    var ring = document.querySelector('.score-ring');
    if (ring) {
      ring.style.setProperty('--score', pg);
      ring.classList.remove('score-red', 'score-orange', 'score-green');
      ring.classList.add(pg <= 70 ? 'score-red' : pg < 100 ? 'score-orange' : 'score-green');
      var num = ring.querySelector('.score-number'); if (num) num.textContent = pg + '%';
    }
    var cap = document.querySelector('.score-caption');
    if (cap) cap.innerHTML = 'Promedio de integridad ' + p + '% y vigencia ' + pv + '%';
    Array.prototype.forEach.call(document.querySelectorAll('.metric'), function (m) {
      var l = (m.querySelector('.metric-label') || {}).textContent || '', n = m.querySelector('.metric-number');
      if (!n) return;
      if (l === '% Integridad') n.textContent = p + '%';
      else if (l === '% Vigencia') n.textContent = pv + '%';
      else if (l === 'Filas modificadas') n.textContent = t.it - t.ii;
    });
  }
  // Resumen de checks al final de cada modelo: cuales estan marcados como Revisado y cuales faltan
  var ST = {PASS: 'Pasa', FAIL: 'Falla', INFO: 'Info'};
  function resumen(rep) {
    var sec = rep.querySelector('[data-rev-sum]'); if (!sec) return;
    var box = sec.querySelector('.rev-sum-box'), grupos = {}, orden = [], tot = 0, hechos = 0;
    Array.prototype.forEach.call(rep.querySelectorAll('.check-card[data-key]'), function (card) {
      var chk = card.querySelector('.rev-chk'); if (!chk || card.classList.contains('val-empty')) return;
      var s = (card.closest('.section') || {}).getAttribute ? card.closest('.section').getAttribute('data-section') : '';
      if (!grupos[s]) { grupos[s] = []; orden.push(s); }
      grupos[s].push(card); tot++; if (chk.checked) hechos++;
    });
    var falta = tot - hechos, pc = tot ? Math.round(100 * hechos / tot) : 0;
    sec.querySelector('.rev-sum-count').textContent = hechos + ' de ' + tot + ' revisados';
    var h = '<div class="rs-head"><span class="rs-big">' + hechos + '<small>/ ' + tot + '</small></span>' +
      '<span class="rs-bar"><i style="width:' + pc + '%"></i></span>' +
      '<span class="rs-msg' + (falta ? '' : ' done') + '">' + (falta ? 'Falta' + (falta === 1 ? ' 1 check' : 'n ' + falta + ' checks') + ' por revisar' : 'Todos los checks están revisados') + '</span></div>';
    orden.forEach(function (s, gi) {
      h += '<div class="rs-grp"><h4>' + esc(s) + '</h4>';
      grupos[s].forEach(function (card, ci) {
        var ok = card.querySelector('.rev-chk').checked, camb = !ok && card.querySelector('.rev-cambio');
        var rc = card.querySelector('.result-count'), st = card.getAttribute('data-status');
        h += '<button type="button" class="rs-row' + (ok ? ' ok' : camb ? ' cambio' : '') + '" data-g="' + gi + '" data-c="' + ci + '"><span class="rs-dot"></span>' +
          '<span class="rs-name">' + esc(card.querySelector('.check-title').textContent) + '<em>' + esc(rc ? rc.textContent : '') + '</em></span>' +
          '<span class="rs-st ' + st + '">' + (ST[st] || st) + '</span>' +
          '<span class="rs-rev">' + (ok ? 'Revisado' : camb ? 'Cambió, revisar' : 'Pendiente') + '</span></button>';
      });
      h += '</div>';
    });
    box.innerHTML = h;
    Array.prototype.forEach.call(box.querySelectorAll('.rs-row'), function (b) {
      b.addEventListener('click', function () {
        var card = grupos[orden[+b.getAttribute('data-g')]][+b.getAttribute('data-c')];
        card.scrollIntoView({behavior: 'smooth', block: 'center'});
        card.classList.remove('rev-flash'); void card.offsetWidth; card.classList.add('rev-flash');
      });
    });
  }
  function esc(t) { return String(t).replace(/[&<>"]/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]; }); }
  // Tablas desplegadas: maximo 10 filas visibles; el resto con el scroll del propio bloque
  function limitar(d) {
    var ts = d.querySelector('.table-scroll'); if (!ts || !d.open) return;
    var trs = Array.prototype.filter.call(ts.querySelectorAll('tr'), function (r) { return r.offsetParent !== null; });
    if (trs.length <= 11) { ts.style.maxHeight = ''; return; }
    var h = 0; for (var k = 0; k <= 10; k++) h += trs[k].getBoundingClientRect().height;
    ts.style.maxHeight = Math.ceil(h + 2) + 'px';
  }
  function limitarTodo() { Array.prototype.forEach.call(document.querySelectorAll('.check-card details[open]'), limitar); }
  document.addEventListener('toggle', function (e) { if (e.target.tagName === 'DETAILS') limitar(e.target); }, true);
  window.addEventListener('resize', limitarTodo);
  function pct(rep) {
    resumen(rep); setTimeout(limitarTodo, 0);
    var meta = JSON.parse(rep.getAttribute('data-val'));
    if (meta.modo === 'exp') return pctExp(rep);
    var c = {OK: meta.base.OK || 0, REVIEW: meta.base.REVIEW || 0, ERROR: meta.base.ERROR || 0};
    filas(rep).forEach(function (tr) { var e0 = tr.getAttribute('data-e0'), e = tr.querySelector('.val-st').value; c[e0]--; c[e]++; });
    var ev = c.OK + c.REVIEW + c.ERROR, p = ev ? Math.round(100 * c.OK / ev) : 0;
    var idx = rep.getAttribute('data-model-index');
    var tab = document.querySelector('.model-option[data-model-index="' + idx + '"] .model-option-score');
    if (tab) tab.textContent = p + '%';
    rep._c = c;
    general();
  }
  // % general del proyecto (anillo, texto y metricas de arriba) = suma de todos los modelos
  function general() {
    var t = {OK: 0, REVIEW: 0, ERROR: 0};
    reports.forEach(function (r) { var c = r._c; if (!c) { var m = JSON.parse(r.getAttribute('data-val')); c = m.base; } t.OK += c.OK || 0; t.REVIEW += c.REVIEW || 0; t.ERROR += c.ERROR || 0; });
    var ev = t.OK + t.REVIEW + t.ERROR, p = ev ? Math.round(100 * t.OK / ev) : 0;
    var ring = document.querySelector('.score-ring');
    if (ring) {
      ring.style.setProperty('--score', p);
      ring.classList.remove('score-red', 'score-orange', 'score-green');
      ring.classList.add(p <= 70 ? 'score-red' : p < 95 ? 'score-orange' : 'score-green');
      ring.setAttribute('aria-label', 'Puntuación: ' + p + ' por ciento');
      var num = ring.querySelector('.score-number'); if (num) num.textContent = p + '%';
    }
    var cap = document.querySelector('.score-caption');
    if (cap) cap.innerHTML = t.OK + ' de ' + ev + ' conceptos coinciden<br>con la Base de Datos.';
    Array.prototype.forEach.call(document.querySelectorAll('.metric'), function (m) {
      var l = (m.querySelector('.metric-label') || {}).textContent || '', n = m.querySelector('.metric-number');
      if (!n) return;
      if (l === 'OK') n.textContent = t.OK;
      else if (l === 'Conceptos evaluados') n.textContent = ev;
      else if (l.indexOf('Errores') === 0) n.textContent = t.ERROR + ' / ' + t.REVIEW;
    });
  }
  function estado() {
    var sucios = reports.filter(function (r) { return r._sucio; });
    if (!nota) return;
    nota.classList.toggle('val-unsaved', sucios.length > 0);
    var bs = document.getElementById('val-save'); if (bs) bs.classList.toggle('val-pendiente', sucios.length > 0);
    var n = 0; reports.forEach(function (r) { n += filas(r).filter(function (tr) { return tr.querySelector('.val-st').value !== tr.getAttribute('data-o'); }).length; });
    nota.textContent = sucios.length ? 'Validaciones sin guardar en ' + sucios.length + ' modelo(s). Presiona "Guardar validaciones".' :
      (n ? n + ' concepto(s) con estatus validado manualmente.' : '');
  }
  function cambio(rep) { rep._sucio = true; pct(rep); estado(); }
  reports.forEach(function (rep) {
    filas(rep).forEach(function (tr) {
      segmento(tr);
      var chk = tr.querySelector('.val-sel'), card = tr.closest('.check-card');
      if (chk && card) chk.addEventListener('change', function () { contarSel(card); });
      var sel = tr.querySelector('.val-st'); sel.value = tr.getAttribute('data-e0'); pintar(tr);
      sel.addEventListener('change', function () { pintar(tr); cambio(rep); });
    });
    Array.prototype.forEach.call(rep.querySelectorAll('.val-bar'), function (bar) {
      var card = bar.closest('.check-card');
      bar.querySelector('.val-all').addEventListener('change', function (ev) {
        Array.prototype.forEach.call(card.querySelectorAll('.val-sel'), function (c) { c.checked = ev.target.checked; });
        contarSel(card);
      });
      Array.prototype.forEach.call(bar.querySelectorAll('[data-val-bulk]'), function (b) {
        b.addEventListener('click', function () {
          var e = b.getAttribute('data-val-bulk'), n = 0;
          Array.prototype.forEach.call(card.querySelectorAll('tr.val-row'), function (tr) {
            var c = tr.querySelector('.val-sel');
            if (c.checked) { tr.querySelector('.val-st').value = e; pintar(tr); c.checked = false; n++;
              tr.classList.remove('val-pulse'); void tr.offsetWidth; tr.classList.add('val-pulse'); }
          });
          bar.querySelector('.val-all').checked = false; contarSel(card);
          if (!n) { alert('No hay conceptos seleccionados en este apartado.'); return; }
          cambio(rep);
        });
      });
    });
    var meta0 = JSON.parse(rep.getAttribute('data-val')), rv = meta0.revisados || {};
    Array.prototype.forEach.call(rep.querySelectorAll('.check-card[data-key]'), function (card) {
      var chk = card.querySelector('.rev-chk'); if (!chk) return;
      var k = card.getAttribute('data-key'), g = rv[k];
      chk.checked = !!(g && g.firma === card.getAttribute('data-sig'));
      card.classList.toggle('revisado', chk.checked);
      if (g && !chk.checked) {
        var n = document.createElement('span'); n.className = 'rev-cambio';
        n.textContent = 'Cambió desde la revisión del ' + String(g.fecha || '').slice(0, 10);
        chk.closest('.status-right').insertBefore(n, chk.closest('.rev-mark'));
      }
      chk.addEventListener('change', function () { card.classList.toggle('revisado', chk.checked); cambio(rep); });
    });
    pct(rep);
  });
  function contenido(rep) {
    var meta = JSON.parse(rep.getAttribute('data-val')), dec = {}, hoy = new Date().toISOString();
    var quitar = [], quitarRev = [];
    filas(rep).forEach(function (tr) {
      var e = tr.querySelector('.val-st').value, o = tr.getAttribute('data-o');
      if (e !== o) dec[tr.getAttribute('data-h')] = {estado: e, fecha: hoy};
      else if (tr.getAttribute('data-e0') !== o) quitar.push(tr.getAttribute('data-h'));  // regresado a su origen
    });
    var rev = {}, prev = meta.revisados || {};
    Array.prototype.forEach.call(rep.querySelectorAll('.check-card[data-key]'), function (card) {
      var chk = card.querySelector('.rev-chk'), k = card.getAttribute('data-key'), sig = card.getAttribute('data-sig');
      if (chk && chk.checked) rev[k] = {firma: sig, fecha: (prev[k] && prev[k].firma === sig) ? prev[k].fecha : hoy};
      else if (chk && prev[k]) quitarRev.push(k);
    });
    return {nombre: meta.archivo, txt: JSON.stringify({version: 1, item_id: meta.item_id, modelo: meta.modelo, actualizado: hoy,
      decisiones: dec, quitar: quitar, revisados: rev, quitar_revisados: quitarRev}, null, 1)};
  }
  var bSave = document.getElementById('val-save'), bClear = document.getElementById('val-clear');
  // ---- Guardar: directo en 03374_5D_VENTAS\validaciones (la carpeta se recuerda en el navegador).
  //      Respaldo: descarga a Descargas; el reporte la recoge al generarse.
  function idb(op, valor) {
    return new Promise(function (ok, mal) {
      var r = indexedDB.open('validaciones5d', 1);
      r.onupgradeneeded = function () { r.result.createObjectStore('h'); };
      r.onerror = function () { mal(r.error); };
      r.onsuccess = function () {
        try {
          var tx = r.result.transaction('h', op === 'get' ? 'readonly' : 'readwrite'), st = tx.objectStore('h');
          var q = op === 'get' ? st.get('carpeta') : op === 'del' ? st.delete('carpeta') : st.put(valor, 'carpeta');
          q.onsuccess = function () { ok(q.result); }; q.onerror = function () { mal(q.error); };
        } catch (e) { mal(e); }
      };
    });
  }
  function combinar(actual, nuevo) {
    var dec = Object.assign({}, actual.decisiones || {}, nuevo.decisiones || {});
    (nuevo.quitar || []).forEach(function (h) { delete dec[h]; });
    var rev = Object.assign({}, actual.revisados || {}, nuevo.revisados || {});
    (nuevo.quitar_revisados || []).forEach(function (k) { delete rev[k]; });
    return {version: 1, item_id: nuevo.item_id, modelo: nuevo.modelo, actualizado: nuevo.actualizado, decisiones: dec, revisados: rev};
  }
  function escribir(dir, a) {
    var nuevo = JSON.parse(a.txt);
    return dir.getFileHandle(a.nombre, {create: true}).then(function (h) {
      return h.getFile().then(function (f) { return f.text(); }).then(function (t) {
        var actual = {}; try { actual = t ? JSON.parse(t) : {}; } catch (e) {}
        return h.createWritable().then(function (w) {
          return w.write(JSON.stringify(combinar(actual, nuevo), null, 1)).then(function () { return w.close(); });
        });
      });
    });
  }
  function descargar(archivos) {
    archivos.forEach(function (a, k) {
      setTimeout(function () {
        var l = document.createElement('a'); l.href = URL.createObjectURL(new Blob([a.txt], {type: 'application/json'}));
        l.download = PREFIJO + a.nombre; document.body.appendChild(l); l.click(); l.remove();
      }, k * 400);
    });
  }
  function carpeta() {
    return idb('get').catch(function () { return null; }).then(function (dir) {
      if (dir) {
        return dir.queryPermission({mode: 'readwrite'}).then(function (p) {
          return p === 'granted' ? p : dir.requestPermission({mode: 'readwrite'});
        }).then(function (p) { if (p !== 'granted') throw new Error('Permiso denegado'); return dir; });
      }
      return window.showDirectoryPicker({id: 'validaciones5d', mode: 'readwrite'}).then(function (d) {
        if (d.name.toLowerCase() !== 'validaciones' &&
            !confirm('La carpeta elegida se llama "' + d.name + '", no "validaciones" (03374_5D_VENTAS\\validaciones). ¿Usarla de todos modos?'))
          throw {name: 'AbortError'};
        return idb('put', d).catch(function () {}).then(function () { return d; });
      });
    });
  }
  function marcarGuardado(sucios, texto) {
    sucios.forEach(function (r) {
      r._sucio = false;
      var base = r._c && r._c.OK !== undefined ? {OK: r._c.OK, REVIEW: r._c.REVIEW, ERROR: r._c.ERROR} : null;
      // lo guardado pasa a ser la base de la pagina (para combinar bien un segundo guardado)
      filas(r).forEach(function (tr) { tr.setAttribute('data-e0', tr.querySelector('.val-st').value); });
      var meta = JSON.parse(r.getAttribute('data-val')), rv = {};
      Array.prototype.forEach.call(r.querySelectorAll('.check-card[data-key]'), function (card) {
        var c = card.querySelector('.rev-chk');
        if (c && c.checked) rv[card.getAttribute('data-key')] = {firma: card.getAttribute('data-sig'), fecha: new Date().toISOString()};
      });
      meta.revisados = rv; if (base && meta.modo !== 'exp') meta.base = base; r.setAttribute('data-val', JSON.stringify(meta));
      r._c = null; pct(r);
    });
    estado(); if (nota) nota.textContent = texto;
  }
  if (bSave) bSave.addEventListener('click', function () {
    var sucios = reports.filter(function (r) { return r._sucio; });
    if (!sucios.length) { alert('No hay validaciones nuevas por guardar.'); return; }
    var archivos = sucios.map(contenido);
    if (!window.showDirectoryPicker || !window.indexedDB) {
      descargar(archivos);
      marcarGuardado(sucios, 'Validaciones descargadas (' + archivos.length + ' modelo(s)). Se aplicarán al generar el reporte 5D.');
      return;
    }
    carpeta().then(function (dir) {
      return archivos.reduce(function (p, a) { return p.then(function () { return escribir(dir, a); }); }, Promise.resolve());
    }).then(function () {
      marcarGuardado(sucios, 'Validaciones guardadas en 03374_5D_VENTAS\\validaciones (' + archivos.length + ' modelo(s)). Se aplican al % oficial en la siguiente corrida del reporte.');
    }).catch(function (e) {
      if (e && e.name === 'AbortError') return;
      if (e && e.name === 'NotFoundError') idb('del').catch(function () {});
      descargar(archivos);
      marcarGuardado(sucios, 'No se pudo escribir en la carpeta (' + ((e && e.message) || e) + '). Se descargaron a Descargas; el reporte las recogerá al generarse.');
    });
  });
  if (bClear) bClear.addEventListener('click', function () {
    var rep = document.querySelector('.model-report.active[data-val]');
    if (!rep) return;
    if (!confirm('¡NO LO HAGAS!, ES IMPORTANTE NO PERDER EL HISTORIAL DE CAMBIOS DE ESTA REVISIÓN, PREGUNTA AL RESPONSABLE DE BIM PRESUPUESTOS SOBRE EL USO DE ESTE BOTÓN')) return;
    if (!confirm('CONFIRMACIÓN FINAL:\n\nTodos los conceptos del modelo seleccionado regresan a su estatus de origen. El cambio se hace efectivo hasta que presiones "Guardar validaciones".\n\n¿Confirmas que tienes autorización?')) return;
    filas(rep).forEach(function (tr) { tr.querySelector('.val-st').value = tr.getAttribute('data-o'); pintar(tr); });
    cambio(rep);
  });
  // ---- Al abrir la pagina: aplicar lo guardado en 03374_5D_VENTAS\validaciones despues de la ultima corrida
  //      (asi no hace falta volver a generar el reporte para ver las validaciones).
  function aplicarGuardado(dir) {
    return reports.reduce(function (p, rep) {
      return p.then(function () {
        var meta = JSON.parse(rep.getAttribute('data-val'));
        return dir.getFileHandle(meta.archivo).then(function (h) { return h.getFile(); })
          .then(function (f) { return f.text(); }).then(function (t) {
            var d = JSON.parse(t), dec = d.decisiones || {}, rv = d.revisados || {};
            filas(rep).forEach(function (tr) {
              var g = dec[tr.getAttribute('data-h')], e = g ? g.estado : tr.getAttribute('data-o');
              tr.querySelector('.val-st').value = e; pintar(tr);
            });
            Array.prototype.forEach.call(rep.querySelectorAll('.check-card[data-key]'), function (card) {
              var c = card.querySelector('.rev-chk'), g = rv[card.getAttribute('data-key')];
              if (!c) return;
              c.checked = !!(g && g.firma === card.getAttribute('data-sig'));
              card.classList.toggle('revisado', c.checked);
            });
            pct(rep);
            return rep;
          }).catch(function () { return null; });
      });
    }, Promise.resolve()).then(function () {
      var cambiados = reports.filter(function (r) { return filas(r).some(function (tr) { return tr.querySelector('.val-st').value !== tr.getAttribute('data-e0'); }); });
      if (cambiados.length) marcarGuardado(cambiados, 'Se aplicaron las validaciones guardadas después de la última corrida del reporte. El % oficial del índice se actualiza al volver a generarlo.');
      else estado();
    });
  }
  if (window.showDirectoryPicker && window.indexedDB) {
    idb('get').then(function (dir) {
      if (!dir) return;
      dir.queryPermission({mode: 'read'}).then(function (p) {
        if (p === 'granted') return aplicarGuardado(dir);
        // Chrome pide permiso con un clic del usuario: se ofrece un boton en la barra
        var b = document.createElement('button');
        b.className = 'pill-button val-pendiente'; b.type = 'button'; b.id = 'val-load';
        b.innerHTML = '<span>Cargar validaciones guardadas</span>';
        var ref = document.getElementById('val-save'); if (ref) ref.parentNode.insertBefore(b, ref);
        if (nota) nota.textContent = 'Presiona "Cargar validaciones guardadas" para ver lo validado después de la última corrida del reporte.';
        b.addEventListener('click', function () {
          dir.requestPermission({mode: 'readwrite'}).then(function (q) {
            if (q !== 'granted') return;
            b.remove(); return aplicarGuardado(dir);
          });
        });
      });
    }).catch(function () {});
  }
  window.addEventListener('beforeunload', function (e) {
    if (reports.some(function (r) { return r._sucio; })) { e.preventDefault(); e.returnValue = ''; }
  });
  estado();
}());
"""
