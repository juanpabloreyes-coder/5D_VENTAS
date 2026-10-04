"""Catalogo PPTO MAESTRO (Base de Datos de Presupuestos) leido en el reporte, con la MISMA limpieza y la misma
busqueda que el add-in (Catalogo5D.cs), para mostrar junto a cada discrepancia el valor que espera el catalogo
y resaltar exactamente lo que no coincide."""
import csv
import io
import logging
import re
from pathlib import Path

log = logging.getLogger("cat5d_sync.catalogo_bd")
_cache = {}


def clean(v):
    if v is None:
        return ""
    if isinstance(v, float):
        v = (str(int(v)) + ".0") if v.is_integer() else repr(v)
    s = str(v).strip().replace("\r", " ").replace("\n", " ")
    while "  " in s:
        s = s.replace("  ", " ")
    return s


def _num(s):
    try:
        return float(s)
    except Exception:
        return None


def code(v):
    v = clean(v)
    if not v:
        return ""
    v = v.replace(",", "")
    n = _num(v)
    if n is not None and n == 0:
        return ""
    if re.fullmatch(r"\d+\.0+", v):
        v = v.split(".")[0]
    n = _num(v)
    if n is not None and n == int(n) and abs(n) < 9.2e18:
        v = str(int(n))
    return v.strip()


def control(v):
    v = clean(v)
    if not v:
        return ""
    v = v.replace(",", "")
    if "." in v:
        v = v.split(".")[0]
    v = v.strip()
    n = _num(v)
    if n is not None and n == 0:
        return ""
    if re.fullmatch(r"\d+", v):
        v = v.zfill(3) if len(v) < 3 else v[:3]
    return v


def k(v):
    return clean(v).upper()


def leer(ruta):
    """-> {"BASE": {tipo_k: [item]}, "ADD": {...}}  item = {control, codigo, descripcion, unidad, partida} (texto original)"""
    ruta = Path(ruta)
    clave = (str(ruta), ruta.stat().st_mtime, ruta.stat().st_size)
    if clave in _cache:
        return _cache[clave]
    b = ruta.read_bytes()
    try:
        texto = b.decode("utf-8")
    except UnicodeDecodeError:
        texto = b.decode("latin-1")
    texto = texto.lstrip("﻿")
    cat = {"BASE": {}, "ADD": {}}
    modo, tipo_b, tipo_a = "BASE", None, None
    for row in csv.reader(io.StringIO(texto)):
        if not row:
            continue
        row = list(row) + [""] * (6 - len(row))
        col_a = k(row[0])
        if col_a in ("CONCEPTOS BASE", "---BASE---", "BASE"):
            modo = "BASE"; continue
        if col_a in ("CONCEPTOS ADD", "---ADD---", "ADD"):
            modo = "ADD"; continue
        tipo, codigo = clean(row[0]), code(row[2])
        if codigo.lower() in ("codigo", "código") or tipo.lower() in ("tipo", "tipo (revit)"):
            continue
        if modo == "BASE":
            if tipo:
                tipo_b = tipo
            t = tipo_b
        else:
            if tipo:
                tipo_a = tipo
            t = tipo_a
        if not t or not codigo:
            continue
        cat[modo].setdefault(k(t), []).append({"control": control(row[1]), "codigo": codigo, "descripcion": clean(row[3]),
                                               "unidad": clean(row[4]), "partida": clean(row[5])})
    _cache[clave] = cat
    return cat


def tipo_catalogo(tipo, cat):
    tk = k(tipo)
    if not tk:
        return ""
    if tk in cat:
        return tk
    pref = [x for x in cat if tk.startswith(x)]
    return max(pref, key=len) if pref else ""


def esperado(f, catalogos):
    """Concepto del catalogo con el que se comparo la fila (mismo tipo y codigo; el de menos diferencias).
    f: fila del add-in [ID, cat, tipo, alcance, concepto, control, codigo, descripcion, unidad, partida, ...]
    -> dict con control/descripcion/unidad/partida esperados, o {"codigos": [...]} si el codigo no es del tipo."""
    if not catalogos:
        return None
    cat = catalogos["BASE" if f[3] == "BASE" else "ADD"]
    ctk = tipo_catalogo(f[2], cat)
    if not ctk:
        return None
    ck = code(f[6]).upper()
    items = [i for i in cat[ctk] if i["codigo"].upper() == ck]
    if not items:
        return {"codigos": sorted({i["codigo"] for i in cat[ctk]})}

    def difs(i):
        return sum([k(f[7]) != k(i["descripcion"]), k(f[8]) != k(i["unidad"]),
                    control(f[5]).upper() != i["control"].upper(),
                    bool(i["partida"]) and k(f[9]) != k(i["partida"])])
    return min(items, key=difs)
