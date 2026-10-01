// ExcelXlsx.cs -- Sync5D: escribe el .xlsx del presupuesto a partir de la plantilla limpia
// (Recursos\Plantilla_Presupuesto_5D.xlsx = Catalogo.xlsm del GCP_PLUGIN sin macros ni botones).
// Se hace con Open XML "a mano" (System.IO.Compression + System.Xml.Linq) para no cargar librerias de Excel
// dentro de Revit: GCP_PLUGIN ya trae otras versiones de ClosedXML/OpenXml y chocarian.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Text;
using System.Xml.Linq;

namespace Ventas5D.Sync5D
{
    internal static class ExcelXlsx
    {
        static readonly XNamespace S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
        static readonly XNamespace R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
        static readonly XNamespace PR = "http://schemas.openxmlformats.org/package/2006/relationships";
        static readonly XNamespace CT = "http://schemas.openxmlformats.org/package/2006/content-types";
        const string TipoHoja = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet";
        const string CtHoja = "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml";

        // Estilos de la plantilla (ver styles.xml): 18 = texto (columna A), 27 = negrita, 28 = texto + negrita
        public const int EstiloTexto = 18, EstiloNegrita = 27, EstiloTextoNegrita = 28;

        public static void Escribir(byte[] plantilla, Hoja hoja1, Hoja hoja2, List<Hoja> pestanas, Hoja meta, string destino)
        {
            using var ms = new MemoryStream();
            ms.Write(plantilla, 0, plantilla.Length);
            ms.Position = 0;
            using (var zip = new ZipArchive(ms, ZipArchiveMode.Update, true))
            {
                CompletarHoja(zip, "xl/worksheets/sheet1.xml", hoja1, true);
                CompletarHoja(zip, "xl/worksheets/sheet2.xml", hoja2, true);

                var wb = Cargar(zip, "xl/workbook.xml");
                var rels = Cargar(zip, "xl/_rels/workbook.xml.rels");
                var ct = Cargar(zip, "[Content_Types].xml");
                var sheets = wb.Root.Element(S + "sheets");
                var sheetId = sheets.Elements(S + "sheet").Max(e => (int)e.Attribute("sheetId")) + 1;

                var todas = pestanas.ToList();
                if (meta != null) todas.Add(meta);
                var nombres = new HashSet<string>(sheets.Elements(S + "sheet").Select(e => (string)e.Attribute("name")),
                                                  StringComparer.OrdinalIgnoreCase);
                var n = 3;
                foreach (var h in todas)
                {
                    var nombre = NombreUnico(h.Nombre, nombres);
                    h.Nombre = nombre;
                    var parte = $"worksheets/sheet{n}.xml";
                    var rid = "rIdS" + n;
                    Guardar(zip, "xl/" + parte, HojaNueva(h));
                    var el = new XElement(S + "sheet", new XAttribute("name", nombre),
                        new XAttribute("sheetId", sheetId++), new XAttribute(R + "id", rid));
                    if (h.Oculta) el.Add(new XAttribute("state", "veryHidden"));
                    sheets.Add(el);
                    rels.Root.Add(new XElement(PR + "Relationship", new XAttribute("Id", rid),
                        new XAttribute("Type", TipoHoja), new XAttribute("Target", parte)));
                    ct.Root.Add(new XElement(CT + "Override", new XAttribute("PartName", "/xl/" + parte),
                        new XAttribute("ContentType", CtHoja)));
                    n++;
                }
                Guardar(zip, "xl/workbook.xml", wb);
                Guardar(zip, "xl/_rels/workbook.xml.rels", rels);
                Guardar(zip, "[Content_Types].xml", ct);
            }
            Directory.CreateDirectory(Path.GetDirectoryName(destino));
            File.WriteAllBytes(destino, ms.ToArray());
        }

        // Deja los nombres finales de las pestanas (validos y sin repetir) antes de guardar nada, para que la
        // foto de la exportacion use exactamente los mismos nombres que el Excel.
        public static void AsignarNombres(IEnumerable<Hoja> hojas)
        {
            var usados = new HashSet<string>(new[] { "Hoja1", "Hoja2" }, StringComparer.OrdinalIgnoreCase);
            foreach (var h in hojas) h.Nombre = NombreUnico(h.Nombre, usados);
        }

        // Nombres de pestana validos para Excel: sin []:*?/\ , maximo 31 caracteres, sin repetir.
        static string NombreUnico(string nombre, HashSet<string> usados)
        {
            var limpio = new string((nombre ?? "Tabla").Select(c => "[]:*?/\\".IndexOf(c) >= 0 ? '_' : c).ToArray()).Trim('\'');
            if (limpio.Length == 0) limpio = "Tabla";
            if (limpio.Length > 31) limpio = limpio.Substring(0, 31);
            var final = limpio;
            for (var i = 1; usados.Contains(final); i++)
            {
                var suf = $" ({i})";
                final = (limpio.Length + suf.Length > 31 ? limpio.Substring(0, 31 - suf.Length) : limpio) + suf;
            }
            usados.Add(final);
            return final;
        }

        // Agrega las celdas de 'datos' a una hoja existente de la plantilla, conservando su formato.
        static void CompletarHoja(ZipArchive zip, string parte, Hoja datos, bool colATexto)
        {
            var doc = Cargar(zip, parte);
            var sd = doc.Root.Element(S + "sheetData");
            for (int r = 1; r <= datos.Celdas.Count; r++)
            {
                var fila = datos.Celdas[r - 1];
                for (int c = 1; c <= fila.Count; c++)
                {
                    var v = fila[c - 1];
                    if (Hoja.Vacia(v)) continue;
                    var row = Fila(sd, r);
                    var celda = Celda(row, r, c);
                    var neg = datos.EsNegrita(r, c);
                    int? estilo = c == 1 && colATexto ? (neg ? EstiloTextoNegrita : EstiloTexto) : neg ? EstiloNegrita : (int?)null;
                    if (estilo == null && celda.Attribute("s") != null) estilo = (int)celda.Attribute("s");
                    Llenar(celda, v, estilo);
                }
            }
            AjustarAnchos(doc, datos);
            // La dimension de la plantilla ya no aplica; Excel la recalcula.
            doc.Root.Element(S + "dimension")?.Remove();
            Guardar(zip, parte, doc);
        }

        // Ancho de columnas B-E segun el texto mas largo de los conceptos (desde la fila 10; arriba esta el
        // encabezado de la plantilla). Nunca mas angosto que la plantilla ni mas de 80.
        static void AjustarAnchos(XDocument doc, Hoja datos)
        {
            var cols = doc.Root.Element(S + "cols");
            if (cols == null)
            {
                cols = new XElement(S + "cols");
                var antes = doc.Root.Element(S + "sheetData");
                antes.AddBeforeSelf(cols);
            }
            // Separar rangos min-max en columnas individuales para poder ajustar cada una
            foreach (var col in cols.Elements(S + "col").ToList())
            {
                int a = (int)col.Attribute("min"), b = (int)col.Attribute("max");
                if (a == b) continue;
                for (int c = a; c <= b; c++)
                {
                    var nueva = new XElement(col);
                    nueva.SetAttributeValue("min", c); nueva.SetAttributeValue("max", c);
                    col.AddBeforeSelf(nueva);
                }
                col.Remove();
            }
            int[] minimos = { 0, 0, 25, 45, 10, 14 }; // indice = columna (B codigo, C descripcion, D unidad, E cantidad)
            for (int c = 2; c <= 5; c++)
            {
                int largo = 0;
                for (int r = 10; r <= datos.Celdas.Count; r++)
                {
                    var fila = datos.Celdas[r - 1];
                    if (c <= fila.Count) largo = Math.Max(largo, Hoja.Texto(fila[c - 1]).Length);
                }
                var col = cols.Elements(S + "col").FirstOrDefault(e => (int)e.Attribute("min") == c);
                double actual = col != null ? double.Parse((string)col.Attribute("width") ?? "0", CultureInfo.InvariantCulture) : 0;
                double ancho = Math.Min(80, Math.Max(Math.Max(actual, minimos[c]), largo * 1.1 + 2));
                if (col == null)
                {
                    col = new XElement(S + "col", new XAttribute("min", c), new XAttribute("max", c));
                    var sig = cols.Elements(S + "col").FirstOrDefault(e => (int)e.Attribute("min") > c);
                    if (sig != null) sig.AddBeforeSelf(col); else cols.Add(col);
                }
                col.SetAttributeValue("width", Math.Round(ancho, 2).ToString(CultureInfo.InvariantCulture));
                col.SetAttributeValue("customWidth", 1);
                col.Attribute("bestFit")?.Remove();
            }
        }

        static XElement Fila(XElement sd, int r)
        {
            var row = sd.Elements(S + "row").FirstOrDefault(e => (int)e.Attribute("r") == r);
            if (row != null) return row;
            row = new XElement(S + "row", new XAttribute("r", r));
            var siguiente = sd.Elements(S + "row").FirstOrDefault(e => (int)e.Attribute("r") > r);
            if (siguiente != null) siguiente.AddBeforeSelf(row); else sd.Add(row);
            row.Attribute("spans")?.Remove();
            return row;
        }

        static XElement Celda(XElement row, int r, int c)
        {
            row.Attribute("spans")?.Remove();
            var refe = Columna(c) + r;
            var cel = row.Elements(S + "c").FirstOrDefault(e => (string)e.Attribute("r") == refe);
            if (cel != null) return cel;
            cel = new XElement(S + "c", new XAttribute("r", refe));
            var siguiente = row.Elements(S + "c").FirstOrDefault(e => ColDe((string)e.Attribute("r")) > c);
            if (siguiente != null) siguiente.AddBeforeSelf(cel); else row.Add(cel);
            return cel;
        }

        static void Llenar(XElement cel, object v, int? estilo)
        {
            cel.RemoveNodes();
            cel.Attribute("t")?.Remove();
            cel.Attribute("s")?.Remove();
            if (estilo != null) cel.Add(new XAttribute("s", estilo.Value));
            // Todo se escribe como texto (codigos, cantidades y descripciones), por indicacion del usuario.
            {
                cel.Add(new XAttribute("t", "inlineStr"));
                var t = new XElement(S + "t", XmlSeguro(Hoja.Texto(v)));
                t.Add(new XAttribute(XNamespace.Xml + "space", "preserve"));
                cel.Add(new XElement(S + "is", t));
            }
        }

        static XDocument HojaNueva(Hoja h)
        {
            var sd = new XElement(S + "sheetData");
            for (int r = 1; r <= h.Celdas.Count; r++)
            {
                var row = new XElement(S + "row", new XAttribute("r", r));
                var fila = h.Celdas[r - 1];
                for (int c = 1; c <= fila.Count; c++)
                {
                    if (Hoja.Vacia(fila[c - 1])) continue;
                    var cel = new XElement(S + "c", new XAttribute("r", Columna(c) + r));
                    Llenar(cel, fila[c - 1], h.EsNegrita(r, c) ? EstiloNegrita : (int?)null);
                    row.Add(cel);
                }
                if (row.HasElements) sd.Add(row);
            }
            return new XDocument(new XDeclaration("1.0", "UTF-8", "yes"),
                new XElement(S + "worksheet", new XAttribute(XNamespace.Xmlns + "r", R.NamespaceName), sd));
        }

        static string XmlSeguro(string s)
        {
            var sb = new StringBuilder(s.Length);
            foreach (var ch in s)
                if (ch == '\t' || ch == '\n' || ch == '\r' || (ch >= 0x20 && ch <= 0xD7FF) || (ch >= 0xE000 && ch <= 0xFFFD)) sb.Append(ch);
            return sb.ToString();
        }

        public static string Columna(int c)
        {
            var s = "";
            while (c > 0) { var m = (c - 1) % 26; s = (char)('A' + m) + s; c = (c - 1) / 26; }
            return s;
        }

        static int ColDe(string refe)
        {
            int c = 0;
            foreach (var ch in refe) { if (!char.IsLetter(ch)) break; c = c * 26 + (char.ToUpperInvariant(ch) - 'A' + 1); }
            return c;
        }

        static XDocument Cargar(ZipArchive zip, string parte)
        {
            var e = zip.GetEntry(parte) ?? throw new InvalidDataException("La plantilla no tiene " + parte);
            using var s = e.Open();
            return XDocument.Load(s);
        }

        static void Guardar(ZipArchive zip, string parte, XDocument doc)
        {
            zip.GetEntry(parte)?.Delete();
            var e = zip.CreateEntry(parte, CompressionLevel.Optimal);
            using var s = e.Open();
            using var w = new StreamWriter(s, new UTF8Encoding(false));
            doc.Save(w, SaveOptions.DisableFormatting);
        }
    }
}
