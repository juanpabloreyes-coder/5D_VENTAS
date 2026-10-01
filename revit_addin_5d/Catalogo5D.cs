// Catalogo5D.cs -- 5D_VENTAS (modulo "Base de Datos vs Revit" del add-in Sync5D)
// Traduccion 1:1 del boton de pyRevit "5D Comparativa Base Datos vs Revit"
// (Auditorias.extension / SQDCM.tab / 5D Catalogos.panel / 5D Base Datos vs Revit.pushbutton / script.py),
// para que corra solo al sincronizar, sin elegir archivo ni vista:
//   - Catalogo: el .csv mas reciente de la carpeta 03374_5D_VENTAS (hoy "PPTO MAESTRO 2025 - REVIT - METRICAS.csv").
//     Para actualizarlo basta con reemplazar el CSV en esa carpeta.
//   - Elementos: los visibles en la vista 3D "ACC" del modelo (la misma vista de coordinacion que pide el Checker),
//     en lugar de la vista 3D activa.
// Mismas reglas de limpieza, mismo cruce por tipo (con tipo base por prefijo), mismos conceptos BASE / AC / REC / ADD,
// mismos conteos de parametros capturados, campos en blanco y residuos aislados.
// Si se cambia una regla en script.py, hay que replicarla aqui (y subir Revision5D.Version).

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using Autodesk.Revit.DB;

namespace Ventas5D.Sync5D
{
    internal sealed class ConceptoCatalogo
    {
        public string control, codigo, descripcion, unidad, partida;
    }

    internal static class Limpieza
    {
        // clean(): quita espacios, saltos de linea y dobles espacios
        public static string Clean(object value)
        {
            if (value == null) return "";
            var s = value is double d ? PyFloat(d) : Convert.ToString(value, CultureInfo.InvariantCulture) ?? "";
            s = s.Trim().Replace("\r", " ").Replace("\n", " ");
            while (s.Contains("  ")) s = s.Replace("  ", " ");
            return s;
        }

        // str(float) de Python: 3.0 -> "3.0", 2.5 -> "2.5"
        public static string PyFloat(double d)
        {
            if (Math.Abs(d) < 1e16 && d == Math.Floor(d)) return ((long)d).ToString(CultureInfo.InvariantCulture) + ".0";
            return d.ToString("R", CultureInfo.InvariantCulture);
        }

        public static string Text(object v) => Clean(v);

        static bool Num(string s, out double d) =>
            double.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out d);

        public static string Code(object value)
        {
            var v = Clean(value);
            if (v.Length == 0) return "";
            v = v.Replace(",", "");
            if (Num(v, out var z) && z == 0) return "";
            if (Regex.IsMatch(v, @"^\d+\.0+$")) v = v.Split('.')[0];
            if (Num(v, out var n) && n == Math.Floor(n) && !double.IsInfinity(n) && Math.Abs(n) < 9.2e18)
                v = ((long)n).ToString(CultureInfo.InvariantCulture);
            return v.Trim();
        }

        // Solo lo que esta a la izquierda del punto: 195.01 -> 195 / 25.99 -> 025 / 7.50 -> 007
        public static string Control(object value)
        {
            var v = Clean(value);
            if (v.Length == 0) return "";
            v = v.Replace(",", "");
            if (v.Contains(".")) v = v.Split('.')[0];
            v = v.Trim();
            if (Num(v, out var z) && z == 0) return "";
            if (Regex.IsMatch(v, @"^\d+$"))
            {
                if (v.Length < 3) v = v.PadLeft(3, '0');
                else if (v.Length > 3) v = v.Substring(0, 3);
            }
            return v;
        }

        public static string KText(object v) => Text(v).ToUpperInvariant();
        public static string KCode(object v) => Code(v).ToUpperInvariant();
        public static string KControl(object v) => Control(v).ToUpperInvariant();

        public static List<string> UniqueClean(IEnumerable<string> values)
        {
            var r = new List<string>();
            foreach (var v in values) { var c = Text(v); if (c.Length > 0 && !r.Contains(c)) r.Add(c); }
            return r;
        }

        public static List<string> UniqueKey(IEnumerable<string> values)
        {
            var r = new List<string>();
            foreach (var v in values) { var c = KText(v); if (c.Length > 0 && !r.Contains(c)) r.Add(c); }
            return r;
        }
    }

    internal sealed class Catalogo5D
    {
        public Dictionary<string, List<ConceptoCatalogo>> Base = new Dictionary<string, List<ConceptoCatalogo>>();
        public Dictionary<string, List<ConceptoCatalogo>> Add = new Dictionary<string, List<ConceptoCatalogo>>();

        static Catalogo5D _cache;
        static string _cacheClave;

        // El .csv mas reciente de la carpeta (no subcarpetas). Se lee una sola vez por sesion de Revit
        // mientras el archivo no cambie.
        public static Catalogo5D Cargar(string carpeta, out string archivo)
        {
            var f = new DirectoryInfo(carpeta).GetFiles("*.csv", SearchOption.TopDirectoryOnly)
                .OrderByDescending(x => x.LastWriteTimeUtc).FirstOrDefault();
            if (f == null) throw new FileNotFoundException("No hay catalogo .csv en " + carpeta);
            archivo = f.Name;
            var clave = f.FullName + "|" + f.LastWriteTimeUtc.Ticks + "|" + f.Length;
            if (_cache != null && _cacheClave == clave) return _cache;
            var c = Leer(File.ReadAllBytes(f.FullName));
            _cache = c; _cacheClave = clave;
            return c;
        }

        static Catalogo5D Leer(byte[] bytes)
        {
            // UTF-8 si es valido; si no, Latin-1 (asi lo leia IronPython en el boton).
            string texto;
            try { texto = new UTF8Encoding(false, true).GetString(bytes); }
            catch (DecoderFallbackException) { texto = Encoding.Latin1.GetString(bytes); }
            if (texto.Length > 0 && texto[0] == '﻿') texto = texto.Substring(1);

            var cat = new Catalogo5D();
            var modo = "BASE";
            string tipoBase = null, tipoAdd = null;
            foreach (var row0 in Csv(texto))
            {
                if (row0.Count == 0) continue;
                var row = row0.ToList();
                while (row.Count < 6) row.Add("");

                var colA = Limpieza.KText(row[0]);
                if (colA == "CONCEPTOS BASE" || colA == "---BASE---" || colA == "BASE") { modo = "BASE"; continue; }
                if (colA == "CONCEPTOS ADD" || colA == "---ADD---" || colA == "ADD") { modo = "ADD"; continue; }

                var tipo = Limpieza.Text(row[0]);
                var control = Limpieza.Control(row[1]);
                var codigo = Limpieza.Code(row[2]);
                var descripcion = Limpieza.Text(row[3]);
                var unidad = Limpieza.Text(row[4]);
                var partida = Limpieza.Text(row[5]);

                var cl = codigo.ToLowerInvariant();
                if (cl == "codigo" || cl == "código") continue;
                var tl = tipo.ToLowerInvariant();
                if (tl == "tipo" || tl == "tipo (revit)") continue;

                if (modo == "BASE")
                {
                    if (tipo.Length > 0) tipoBase = tipo;
                    if (tipoBase == null || codigo.Length == 0) continue;
                    Agregar(cat.Base, tipoBase, control, codigo, descripcion, unidad, partida);
                }
                else
                {
                    if (tipo.Length > 0) tipoAdd = tipo;
                    if (tipoAdd == null || codigo.Length == 0) continue;
                    Agregar(cat.Add, tipoAdd, control, codigo, descripcion, unidad, partida);
                }
            }
            return cat;
        }

        static void Agregar(Dictionary<string, List<ConceptoCatalogo>> cat, string tipo, string control, string codigo,
                            string descripcion, string unidad, string partida)
        {
            var tk = Limpieza.KText(tipo);
            var ck = Limpieza.KCode(codigo);
            if (tk.Length == 0 || ck.Length == 0) return;
            if (!cat.TryGetValue(tk, out var l)) { l = new List<ConceptoCatalogo>(); cat[tk] = l; }
            l.Add(new ConceptoCatalogo
            {
                control = Limpieza.KControl(control), codigo = ck, descripcion = Limpieza.KText(descripcion),
                unidad = Limpieza.KText(unidad), partida = Limpieza.KText(partida)
            });
        }

        // Lector CSV (comillas dobles, comas y saltos de linea dentro de comillas), como csv.reader.
        static IEnumerable<List<string>> Csv(string t)
        {
            var row = new List<string>();
            var sb = new StringBuilder();
            bool q = false, any = false;
            for (int i = 0; i < t.Length; i++)
            {
                var c = t[i];
                if (q)
                {
                    if (c == '"')
                    {
                        if (i + 1 < t.Length && t[i + 1] == '"') { sb.Append('"'); i++; }
                        else q = false;
                    }
                    else sb.Append(c);
                    continue;
                }
                if (c == '"') { q = true; any = true; }
                else if (c == ',') { row.Add(sb.ToString()); sb.Clear(); any = true; }
                else if (c == '\r' || c == '\n')
                {
                    if (c == '\r' && i + 1 < t.Length && t[i + 1] == '\n') i++;
                    if (any || sb.Length > 0) row.Add(sb.ToString());
                    yield return row;
                    row = new List<string>(); sb.Clear(); any = false;
                }
                else { sb.Append(c); any = true; }
            }
            if (any || sb.Length > 0) { row.Add(sb.ToString()); yield return row; }
        }
    }

    // ------------------------------------------------------------------ salida
    internal sealed class Resultado5D
    {
        public string fecha { get; set; }
        public double duracion_s { get; set; }
        public string version { get; set; }
        public string catalogo { get; set; }
        public string vista { get; set; }
        public string aviso { get; set; }
        public Dictionary<string, int> totales { get; set; } = new Dictionary<string, int>();
        // [id, categoria, tipo, alcance, concepto, control, codigo, descripcion, unidad, partida,
        //  resultado, motivo, campos_en_blanco, residuo_aislado("1"/"")]
        public List<List<string>> filas { get; set; } = new List<List<string>>();
    }

    internal static class Revision5D
    {
        public const string Version = "5d-bd-2026-10";

        static readonly HashSet<string> IgnoreCategories = new HashSet<string>
        {
            "CENTER LINE", "GRIDS", "LEVELS", "VIEWS", "VIEWERS", "VIEWPORTS", "SHEETS", "SCHEDULES", "CAMERAS",
            "SHARED SITE", "SHARED SITES", "RASTER IMAGES", "IMPORTS IN FAMILIES", "IMPORT SYMBOLS",
            "BALUSTERS", "RUNS", "SUPPORTS", "LANDINGS", "TOP RAILS", "RAILINGS", "RAILING SUPPORTS", "HANDRAILS",
            "CURTAIN PANELS", "CURTAIN WALL MULLIONS", "CURTAIN WALL PANELS", "CURTAIN WALL GRIDS", "CURTAIN GRIDS",
            "CURTAIN SYSTEMS", "RECTANGULAR STRAIGHT WALL OPENING", "WALL OPENING",
            "PIPING SYSTEMS", "DUCT SYSTEMS", "ELECTRICAL CIRCUITS", "MECHANICAL EQUIPMENT SETS",
            "<ROOM SEPARATION>", "ROOM SEPARATION", "ROOM SEPARATION LINES", "ROOMS", "SPACES", "AREAS",
            "AREA BOUNDARIES", "ROOM TAGS", "SPACE TAGS", "AREA TAGS"
        };

        static readonly HashSet<string> IgnoreTypeNames = new HashSet<string> { "ARQ_PUNTO_REUNION", "ARQ_PISO_TERRENO" };

        static readonly string[] IgnoreBuiltIn =
        {
            "OST_RoomSeparationLines", "OST_RasterImages", "OST_Views", "OST_Schedules", "OST_Cameras", "OST_Grids",
            "OST_Levels", "OST_CurtainWallMullions", "OST_CurtainWallPanels", "OST_CurtainGrids", "OST_StairsRuns",
            "OST_StairsLandings", "OST_StairsSupports", "OST_StairsRailing", "OST_RailingTopRail",
            "OST_RailingHandRail", "OST_PipingSystem"
        };

        static HashSet<long> _ignoreIds;
        static HashSet<long> IgnoreIds
        {
            get
            {
                if (_ignoreIds != null) return _ignoreIds;
                var s = new HashSet<long>();
                foreach (var n in IgnoreBuiltIn)
                    if (Enum.TryParse<BuiltInCategory>(n, out var bic)) s.Add((long)bic);
                return _ignoreIds = s;
            }
        }

        // Vista 3D de coordinacion "ACC" (la misma regla del Checker). Si hay varias, se prefiere una que
        // ademas diga "3D" en el nombre; luego la de nombre mas corto.
        public static View3D VistaAcc(Document doc)
        {
            return new FilteredElementCollector(doc).OfClass(typeof(View3D)).Cast<View3D>()
                .Where(v => !v.IsTemplate && (v.Name ?? "").ToUpperInvariant().Contains("ACC"))
                .OrderByDescending(v => (v.Name ?? "").ToUpperInvariant().Contains("3D"))
                .ThenBy(v => (v.Name ?? "").Length).ThenBy(v => v.Name)
                .FirstOrDefault();
        }

        sealed class Estado
        {
            public int modelo, ignorados, revisados, base_, add, ok, error, review;
            public int capturados, blancos, conBlancos, residuos;
            public List<object[]> res = new List<object[]>();
        }

        public static Resultado5D Correr(Document doc, Catalogo5D cat)
        {
            var salida = new Resultado5D { version = Version };
            var vista = VistaAcc(doc);
            if (vista == null)
            {
                salida.vista = "";
                salida.aviso = "No existe vista 3D con 'ACC': no se pudo revisar el modelo.";
                return salida;
            }
            salida.vista = vista.Name;
            var st = new Estado();

            foreach (var el in new FilteredElementCollector(doc, vista.Id).WhereElementIsNotElementType())
            {
                st.modelo++;
                if (el.Category == null) { st.ignorados++; continue; }
                if (el.Category.CategoryType != CategoryType.Model) { st.ignorados++; continue; }
                var catName = Limpieza.Text(el.Category.Name);
                var catK = Limpieza.KText(catName);
                if (IgnoreCategories.Contains(catK) || IgnoreIds.Contains(el.Category.Id.Value)) { st.ignorados++; continue; }

                var typeId = el.GetTypeId();
                var te = typeId != null && typeId.Value >= 0 ? doc.GetElement(typeId) : null;
                var typeName = te != null ? TypeName(te) : "";
                var typeK = Limpieza.KText(typeName);
                if (IgnoreTypeNames.Contains(typeK)) { st.ignorados++; continue; }
                if (catK == "GENERIC MODELS" && !typeK.StartsWith("ARQ_")) { st.ignorados++; continue; }
                if (Limpieza.KText(P(el, te, "Frente")) == "DESCARTADO") { st.ignorados++; continue; }

                string tipo, controlB, codigoB, descB, uniB, partB;
                if (te != null)
                {
                    tipo = typeName;
                    controlB = Limpieza.Control(P(el, te, "Control"));
                    codigoB = CodigoValue(el, te);
                    descB = P(el, te, "Descripción");
                    uniB = P(el, te, "Unidad");
                    partB = P(el, te, "Partida");
                }
                else { tipo = "<No Type>"; controlB = codigoB = descB = uniB = partB = ""; }

                st.revisados++;
                Contar(st, controlB, "control"); Contar(st, codigoB, "code"); Contar(st, descB, "text");
                Contar(st, uniB, "text"); Contar(st, partB, "text");
                var blancosB = new List<string>();
                if (!Lleno(controlB, "control")) blancosB.Add("Control");
                if (!Lleno(codigoB, "code")) blancosB.Add("Código");
                if (!Lleno(descB, "text")) blancosB.Add("Descripción");
                if (!Lleno(uniB, "text")) blancosB.Add("Unidad");
                if (!Lleno(partB, "text")) blancosB.Add("Partida");

                var v = Validar(tipo, codigoB, descB, uniB, partB, cat.Base, "BASE", new List<string> { partB }, controlB, true);
                Sumar(st, v.Item1); st.base_++;
                Agregar(st, el, catName, tipo, codigoB, descB, uniB, partB, v, "BASE", "Concepto base", controlB, blancosB, false);

                var partAc = P(el, te, "Partida Ac");
                var partRec = P(el, te, "Partida Rec");
                var partAdd1 = P(el, te, "Partida Add (1)");
                var partAdd2 = P(el, te, "Partida Add (2)");

                foreach (var (alcance, partGeneral) in new[] { ("AC", partAc), ("REC", partRec) })
                {
                    var suf = alcance == "AC" ? "Ac" : "Rec";
                    for (int idx = 1; idx <= 2; idx++)
                    {
                        var cod = P(el, te, $"Código {suf} ({idx})");
                        var des = P(el, te, $"Descripción {suf} ({idx})");
                        var uni = P(el, te, $"Unidad {suf} ({idx})");
                        if (Residuo(cod, des, uni, "")) continue;
                        var lista = new List<(string, string, string)>
                        {
                            (cod, "code", $"Código {suf} ({idx})"), (des, "text", $"Descripción {suf} ({idx})"),
                            (uni, "text", $"Unidad {suf} ({idx})")
                        };
                        ContarAsociados(st, lista);
                        var (blancos, residuo) = BlancosAsociados(lista);
                        var cands = Limpieza.UniqueClean(new[] { partGeneral, partB });
                        var partDisp = string.Join(" / ", cands);
                        var r = Validar(tipo, cod, des, uni, partDisp, cat.Add, "ADD", cands, "", false);
                        Sumar(st, r.Item1); st.add++;
                        Agregar(st, el, catName, tipo, cod, des, uni, partDisp, r, alcance, $"{alcance} ({idx})", "", blancos, residuo);
                    }
                }

                for (int idx = 1; idx <= 12; idx++)
                {
                    var cod = P(el, te, $"Código Add ({idx})");
                    var des = P(el, te, $"Descripción Add ({idx})");
                    var uni = P(el, te, $"Unidad Add ({idx})");
                    var ctl = Limpieza.Control(P(el, te, $"Control Add ({idx})"));
                    if (Residuo(cod, des, uni, ctl)) continue;
                    var lista = new List<(string, string, string)>
                    {
                        (ctl, "control", $"Control Add ({idx})"), (cod, "code", $"Código Add ({idx})"),
                        (des, "text", $"Descripción Add ({idx})"), (uni, "text", $"Unidad Add ({idx})")
                    };
                    ContarAsociados(st, lista);
                    var (blancos, residuo) = BlancosAsociados(lista);
                    var partIdx = P(el, te, $"Partida Add ({idx})");
                    var cands = Limpieza.UniqueClean(new[] { partIdx, partAdd1, partAdd2, partB });
                    var partDisp = string.Join(" / ", cands);
                    var r = Validar(tipo, cod, des, uni, partDisp, cat.Add, "ADD", cands, ctl, true);
                    Sumar(st, r.Item1); st.add++;
                    Agregar(st, el, catName, tipo, cod, des, uni, partDisp, r, "ADD", $"ADD ({idx})", ctl, blancos, residuo);
                }
            }

            // Orden del boton: OK, luego REVIEW, luego ERROR; dentro, por ID, alcance y concepto.
            int Grupo(string s) => s == "OK" ? 0 : s == "REVIEW" ? 1 : 2;
            foreach (var r in st.res
                         .OrderBy(x => Grupo((string)x[10])).ThenBy(x => (long)x[0])
                         .ThenBy(x => (string)x[3], StringComparer.Ordinal).ThenBy(x => (string)x[4], StringComparer.Ordinal))
            {
                salida.filas.Add(r.Select((x, i) => i == 0 ? ((long)x).ToString(CultureInfo.InvariantCulture) : (string)x).ToList());
            }
            salida.totales = new Dictionary<string, int>
            {
                ["modelo"] = st.modelo, ["ignorados"] = st.ignorados, ["revisados"] = st.revisados,
                ["conceptos_base"] = st.base_, ["conceptos_add"] = st.add,
                ["ok"] = st.ok, ["error"] = st.error, ["review"] = st.review, ["evaluados"] = st.ok + st.error + st.review,
                ["parametros_capturados"] = st.capturados, ["parametros_en_blanco"] = st.blancos,
                ["conceptos_con_blancos"] = st.conBlancos, ["residuos_aislados"] = st.residuos
            };
            return salida;
        }

        // ---------------- helpers del script
        static string TypeName(Element te)
        {
            var p = te.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM);
            return p != null ? Limpieza.Text(p.AsString()) : Limpieza.Text(te.Name);
        }

        static string P(Element el, Element te, string nombre)
        {
            if (el == null) return "";
            var p = el.LookupParameter(nombre) ?? te?.LookupParameter(nombre);
            if (p == null) return "";
            try
            {
                switch (p.StorageType)
                {
                    case StorageType.String: return Limpieza.Text(p.AsString());
                    case StorageType.Integer: return Limpieza.Text(p.AsInteger());
                    case StorageType.Double: return Limpieza.Text(p.AsDouble());
                    case StorageType.ElementId: return Limpieza.Text(p.AsElementId().Value);
                }
            }
            catch { }
            return "";
        }

        static string CodigoValue(Element el, Element te)
        {
            var p = el.LookupParameter("Código") ?? te?.LookupParameter("Código");
            if (p == null) return "";
            try
            {
                switch (p.StorageType)
                {
                    case StorageType.Integer: return Limpieza.Code(p.AsInteger());
                    case StorageType.Double: return Limpieza.Code(p.AsDouble());
                    case StorageType.String: return Limpieza.Code(p.AsString());
                    default: return Limpieza.Code(p.AsValueString());
                }
            }
            catch { return ""; }
        }

        static string TipoCatalogo(string tipo, Dictionary<string, List<ConceptoCatalogo>> cat)
        {
            var tk = Limpieza.KText(tipo);
            if (tk.Length == 0) return "";
            if (cat.ContainsKey(tk)) return tk;
            // Tipo base por prefijo: el mas largo que coincida (ARQ_MURO_X_V2 -> ARQ_MURO_X)
            return cat.Keys.Where(k => tk.StartsWith(k, StringComparison.Ordinal))
                      .OrderByDescending(k => k.Length).FirstOrDefault() ?? "";
        }

        // -> (resultado, motivo, es_review_original)
        static (string, string, bool) Validar(string tipo, string codigo, string descripcion, string unidad, string partida,
            Dictionary<string, List<ConceptoCatalogo>> cat, string nombreCat, List<string> partidasCand, string control, bool revisarControl)
        {
            var tk = Limpieza.KText(tipo);
            var ctk = TipoCatalogo(tipo, cat);
            var ck = Limpieza.KCode(codigo);
            var ctrlk = Limpieza.KControl(control);
            var dk = Limpieza.KText(descripcion);
            var uk = Limpieza.KText(unidad);
            var pk = Limpieza.KText(partida);
            var cands = partidasCand == null ? (pk.Length > 0 ? new List<string> { pk } : new List<string>()) : Limpieza.UniqueKey(partidasCand);

            if (ck == "1111111111")
                return ("REVIEW", "Código especial 1111111111: modificación especial del proyecto, requiere revisión visual manual.", true);
            if (ck.Length == 0) return ("ERROR", "Código vacío o cero", false);
            if (ctk.Length == 0) return ("ERROR", $"Tipo no existe en catálogo {nombreCat}", false);

            var encontrado = false;
            var mejor = "";
            foreach (var item in cat[ctk])
            {
                if (ck != item.codigo) continue;
                encontrado = true;
                var dOk = dk == item.descripcion;
                var uOk = uk == item.unidad;
                var cOk = !revisarControl || ctrlk == (item.control ?? "");
                var pOk = item.partida.Length == 0 || cands.Contains(item.partida);
                if (dOk && uOk && pOk && cOk)
                    return ("OK", ctk != tk ? $"Coincide con catálogo {nombreCat} usando tipo base {ctk}" : $"Coincide con catálogo {nombreCat}", false);
                var dif = new List<string>();
                if (revisarControl && !cOk) dif.Add("Control no coincide");
                if (!dOk) dif.Add("Descripción no coincide");
                if (!uOk) dif.Add("Unidad no coincide");
                if (!pOk) dif.Add(cands.Count > 0 ? "Partida no coincide en campos relacionados" : "Partida vacía o no coincide");
                if (dif.Count > 0) mejor = string.Join(", ", dif);
            }
            if (!encontrado) mejor = $"Código no pertenece al tipo en catálogo {nombreCat}";
            if (mejor.Length == 0) mejor = "Datos no coinciden";
            return ("ERROR", mejor, false);
        }

        static bool Residuo(string cod, string des, string uni, string ctl) =>
            Limpieza.Code(cod).Length == 0 && Limpieza.Text(des).Length == 0 && Limpieza.Text(uni).Length == 0 && Limpieza.Control(ctl).Length == 0;

        static bool Lleno(string v, string kind) =>
            kind == "control" ? Limpieza.Control(v).Length > 0 : kind == "code" ? Limpieza.Code(v).Length > 0 : Limpieza.Text(v).Length > 0;

        static void Contar(Estado st, string v, string kind) { if (Lleno(v, kind)) st.capturados++; else st.blancos++; }

        // 0 llenos = grupo vacio; 1 lleno = posible residuo (no cuenta); 2+ = grupo intencional
        static void ContarAsociados(Estado st, List<(string v, string kind, string label)> lista)
        {
            if (lista.Count(x => Lleno(x.v, x.kind)) < 2) return;
            foreach (var x in lista) Contar(st, x.v, x.kind);
        }

        static (List<string>, bool) BlancosAsociados(List<(string v, string kind, string label)> lista)
        {
            var llenos = lista.Count(x => Lleno(x.v, x.kind));
            if (llenos == 0) return (new List<string>(), false);
            if (llenos == 1) return (new List<string>(), true);
            return (lista.Where(x => !Lleno(x.v, x.kind)).Select(x => x.label).ToList(), false);
        }

        static void Sumar(Estado st, string res)
        {
            if (res == "OK") st.ok++;
            else if (res == "REVIEW") st.review++;
            else if (res == "ERROR") st.error++;
        }

        static void Agregar(Estado st, Element el, string cat, string tipo, string codigo, string desc, string uni, string partida,
                            (string, string, bool) v, string alcance, string concepto, string control, List<string> blancos, bool residuo)
        {
            if (blancos.Count > 0) st.conBlancos++;
            if (residuo) st.residuos++;
            st.res.Add(new object[]
            {
                el.Id.Value, cat, tipo, alcance, concepto, control, codigo, desc, uni, partida,
                v.Item1, v.Item2, string.Join(", ", blancos), residuo ? "1" : ""
            });
        }
    }
}
