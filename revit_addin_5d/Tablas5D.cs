// Tablas5D.cs -- Sync5D: lectura de las tablas de planificacion del modelo.
// Mismo contenido que escribe hoy "Exportar Presupuesto" (GCP_PLUGIN) en cada pestana del Excel:
// el cuerpo de la tabla tal como se ve en Revit (texto de cada celda), con el nombre de la tabla en A1.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using Autodesk.Revit.DB;

namespace Ventas5D.Sync5D
{
    internal sealed class Tabla
    {
        public string nombre { get; set; }          // nombre de la tabla en Revit
        public List<List<string>> filas { get; set; } = new List<List<string>>();
    }

    internal sealed class FotoTablas
    {
        public string fecha { get; set; }
        public double duracion_s { get; set; }
        public List<Tabla> tablas { get; set; } = new List<Tabla>();
    }

    internal static class Tablas5D
    {
        // Pestanas que entran al compilado (Hoja1 / Hoja2) y a las comparaciones: nombre que empieza
        // con 3 digitos (000-999).
        // Se ignoran espacios y caracteres invisibles al inicio del nombre.
        public static bool EsDe5D(string nombre) => Regex.IsMatch(Limpio(nombre), @"^[0-9]{3}");
        static string Limpio(string n) => new string((n ?? "").Where(ch => !char.IsControl(ch)
            && System.Globalization.CharUnicodeInfo.GetUnicodeCategory(ch) != System.Globalization.UnicodeCategory.Format).ToArray()).Trim();

        // Diagnostico de la ultima lectura (para explicar por que no se encontraron tablas 5D).
        public static int UltTotal, UltFallidas, UltVacias;
        public static string UltError = "";
        public static List<string> UltNombres = new List<string>();

        // Todas las tablas del modelo (como el boton actual), en el orden en que Revit las entrega.
        public static List<Tabla> Leer(Document doc, bool solo5D)
        {
            var salida = new List<Tabla>();
            var tablas = new FilteredElementCollector(doc).OfClass(typeof(ViewSchedule)).Cast<ViewSchedule>()
                .Where(s => { try { return !s.IsTemplate && !s.IsTitleblockRevisionSchedule && !s.IsInternalKeynoteSchedule; } catch { return true; } })
                .OrderBy(s => { try { return s.Name; } catch { return ""; } }, StringComparer.Ordinal).ToList();
            UltTotal = 0; UltFallidas = 0; UltVacias = 0; UltError = ""; UltNombres = new List<string>();
            // Revit necesita poder "regenerar" la tabla para entregar el texto de sus celdas: se abre una
            // transaccion temporal y al final se deshace (el modelo no se modifica).
            Transaction tx = null;
            try
            {
                if (!doc.IsModifiable && !doc.IsReadOnly)
                {
                    tx = new Transaction(doc, "Sync5D - leer tablas");
                    if (tx.Start() != TransactionStatus.Started) { tx.Dispose(); tx = null; }
                }
            }
            catch (Exception ex) { Log.Escribir("No se pudo abrir transaccion de lectura: " + ex.Message); tx = null; }
            try
            {
            foreach (var s in tablas)
            {
                string nombre = "";
                try { nombre = s.Name; } catch { }
                UltTotal++;
                if (UltNombres.Count < 8) UltNombres.Add(nombre);
                if (solo5D && !EsDe5D(nombre)) continue;
                try
                {
                    var t = LeerTabla(s);
                    // Igual que el boton actual: las tablas sin datos (solo titulo y encabezados) no se exportan.
                    if (t.filas.Count <= 2) { UltVacias++; continue; }
                    salida.Add(t);
                }
                catch (Exception ex)
                {
                    UltFallidas++;
                    if (UltError == "") UltError = $"{nombre}: {ex.GetType().Name} - {ex.Message}";
                    Log.Escribir($"No se pudo leer la tabla '{nombre}': {ex}");
                }
            }
            }
            finally
            {
                try { if (tx != null && tx.HasStarted() && !tx.HasEnded()) tx.RollBack(); } catch { }
                tx?.Dispose();
            }
            Log.Escribir($"Tablas leidas: {salida.Count} de {UltTotal} (vacias {UltVacias}, fallidas {UltFallidas}, 5D {salida.Count(t => EsDe5D(t.nombre))})");
            return salida;
        }

        static Tabla LeerTabla(ViewSchedule s)
        {
            var t = new Tabla { nombre = s.Name };
            var body = s.GetTableData().GetSectionData(SectionType.Body);
            int nf = body.NumberOfRows, nc = body.NumberOfColumns;
            for (int r = 0; r < nf; r++)
            {
                var fila = new List<string>(nc);
                for (int c = 0; c < nc; c++)
                {
                    string txt;
                    try { txt = s.GetCellText(SectionType.Body, r, c) ?? ""; }
                    catch { txt = ""; }
                    fila.Add(txt);
                }
                t.filas.Add(fila);
            }
            // Igual que el Excel actual: el nombre de la tabla ocupa A1 (en lugar del primer encabezado).
            if (t.filas.Count == 0) t.filas.Add(new List<string> { "" });
            if (t.filas[0].Count == 0) t.filas[0].Add("");
            t.filas[0][0] = s.Name;
            // Sin filas vacias al final
            while (t.filas.Count > 1 && t.filas[t.filas.Count - 1].All(string.IsNullOrWhiteSpace))
                t.filas.RemoveAt(t.filas.Count - 1);
            return t;
        }
    }
}
