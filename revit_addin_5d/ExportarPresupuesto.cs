// ExportarPresupuesto.cs -- Sync5D: boton "Exportar Presupuesto" de la pestana 5D.
// Hace lo mismo que el boton del GCP_PLUGIN (una pestana por tabla de Revit con la plantilla del presupuesto)
// y ademas:
//   - deja Hoja1 y Hoja2 compiladas (como las macros, solo pestanas 000-999), sin macros ni botones (.xlsx);
//   - agrega la hoja oculta "_5D_META" con quien/cuando/que modelo y el contenido exacto exportado;
//   - guarda una foto de la exportacion en 03374_5D_VENTAS\exportaciones (para el reporte Exportado vs Revit);
//   - guarda el Excel en <Proyecto>\02_PRESUPUESTOS\021_AUXILIARES\0212_CUANTIFICACIONES\02121_CATALOGOS y lo abre.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.Json;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using WinForm = System.Windows.Forms.Form;
using WinLabel = System.Windows.Forms.Label;
using WinCombo = System.Windows.Forms.ComboBox;
using WinButton = System.Windows.Forms.Button;
using WinResult = System.Windows.Forms.DialogResult;

namespace Ventas5D.Sync5D
{
    [Transaction(TransactionMode.Manual)]
    public class ExportarPresupuesto : IExternalCommand
    {
        public Result Execute(ExternalCommandData data, ref string message, ElementSet elements)
        {
            var doc = data.Application.ActiveUIDocument?.Document;
            if (doc == null || doc.IsFamilyDocument)
            {
                TaskDialog.Show("Exportar Presupuesto", "Abre un modelo de proyecto para exportar el presupuesto.");
                return Result.Cancelled;
            }
            try
            {
                var cfg = Config.Leer() ?? new Config();
                var modelo = Modelo.De(doc);
                var tablas = Tablas5D.Leer(doc, false);
                if (!tablas.Any(t => Tablas5D.EsDe5D(t.nombre)))
                {
                    var diag = $"No se encontraron tablas 5D (nombre que empiece con 000-999).\n\n" +
                               $"Tablas en el modelo: {Tablas5D.UltTotal}\nLeidas: {tablas.Count}\nCon error: {Tablas5D.UltFallidas}" +
                               (Tablas5D.UltError != "" ? $"\nPrimer error: {Tablas5D.UltError}" : "") +
                               "\n\nPrimeros nombres:\n" + string.Join("\n", Tablas5D.UltNombres.Select(n => "[" + n + "]"));
                    Log.Escribir("SIN TABLAS 5D " + diag.Replace("\n", " | "));
                    TaskDialog.Show("Exportar Presupuesto", diag);
                    return Result.Cancelled;
                }

                var frente = PedirFrente(tablas);
                if (frente == null) return Result.Cancelled;

                var ahora = DateTimeOffset.Now;
                var carpeta = ResolverCarpeta(cfg, modelo);
                // Nombre fijo por modelo: al volver a exportar se sobrescribe y ACC/Forma lo guarda como nueva version.
                var nombre = Usuario.Archivo(Path.GetFileNameWithoutExtension(modelo.Titulo)) + ".xlsx";
                var destino = carpeta != null ? Path.Combine(carpeta, nombre) : PedirRuta(nombre);
                if (destino == null) return Result.Cancelled;
                if (EstaAbierto(destino))
                {
                    TaskDialog.Show("Exportar Presupuesto", $"El Excel {Path.GetFileName(destino)} está abierto.\n\nCiérralo y vuelve a exportar para guardar la nueva versión.");
                    return Result.Cancelled;
                }

                var exp = Exportar(doc, cfg, modelo, tablas, frente, ahora, destino);
                Log.Escribir($"EXPORTADO {modelo.Titulo} -> {destino} ({exp})");
                try { Process.Start(new ProcessStartInfo(destino) { UseShellExecute = true }); } catch { }
                return Result.Succeeded;
            }
            catch (Exception ex)
            {
                Log.Escribir("ERROR exportar " + ex);
                TaskDialog.Show("Exportar Presupuesto", "No se pudo exportar el presupuesto:\n\n" + ex.Message);
                return Result.Failed;
            }
        }

        static bool EstaAbierto(string ruta)
        {
            if (!File.Exists(ruta)) return false;
            try { using (new FileStream(ruta, FileMode.Open, FileAccess.ReadWrite, FileShare.None)) { } return false; }
            catch (IOException) { return true; }
            catch { return false; }
        }

        // Devuelve el id de la exportacion.
        internal static string Exportar(Document doc, Config cfg, Modelo modelo, List<Tabla> tablas, string frente,
                                        DateTimeOffset ahora, string destino)
        {
            var exportId = Guid.NewGuid().ToString("N");
            var originales5D = tablas.Where(t => Tablas5D.EsDe5D(t.nombre)).ToList();

            // Hojas en memoria (las pestanas se modifican al compilar, como lo hacia la macro)
            var pestanas = tablas.Select(t =>
            {
                var h = new Hoja(t.nombre);
                for (int r = 0; r < t.filas.Count; r++)
                    for (int c = 0; c < t.filas[r].Count; c++)
                        if (!string.IsNullOrEmpty(t.filas[r][c])) h.Set(r + 1, c + 1, t.filas[r][c]);
                return h;
            }).ToList();
            var hoja1 = new Hoja("Hoja1");
            var hoja2 = new Hoja("Hoja2");
            var orden = Presupuesto.Compilar(pestanas, hoja1, hoja2, frente);
            ExcelXlsx.AsignarNombres(orden);

            // Contenido final que se entrega (para comprobar despues que nadie lo cambio)
            var contenido = new Dictionary<string, List<List<string>>>
            {
                ["Hoja1"] = Filas(hoja1, 10),
                ["Hoja2"] = Filas(hoja2, 10)
            };
            foreach (var h in orden) contenido[h.Nombre] = Filas(h, 1);

            var info = new Dictionary<string, string>
            {
                ["version_formato"] = "1",
                ["export_id"] = exportId,
                ["fecha"] = ahora.ToString("o"),
                ["modelo"] = modelo.Titulo,
                ["model_urn"] = modelo.ModelUrn,
                ["item_id"] = modelo.ItemId ?? "",
                ["project_id"] = modelo.ProjectId,
                ["revit_user"] = doc.Application.Username ?? "",
                ["windows_user"] = Usuario.Windows,
                ["maquina"] = Usuario.Maquina,
                ["frente"] = frente,
                ["archivo"] = Path.GetFileName(destino),
                ["generador"] = "Sync5D " + typeof(ExportarPresupuesto).Assembly.GetName().Version
            };

            // Hoja oculta _5D_META: datos de la exportacion + contenido exacto de cada hoja
            var meta = new Hoja("_5D_META") { Oculta = true };
            int fila = 1;
            foreach (var kv in info) { meta.Set(fila, 1, kv.Key); meta.Set(fila, 2, kv.Value); fila++; }
            fila++;
            meta.Set(fila, 1, "HOJA"); meta.Set(fila, 2, "FILA"); meta.Set(fila, 3, "VALORES"); fila++;
            foreach (var kv in contenido)
            {
                var filasHoja = kv.Value;
                var inicio = kv.Key == "Hoja1" || kv.Key == "Hoja2" ? 10 : 1;
                for (int i = 0; i < filasHoja.Count; i++)
                {
                    if (filasHoja[i].All(string.IsNullOrEmpty)) continue;
                    meta.Set(fila, 1, kv.Key);
                    meta.Set(fila, 2, (inicio + i).ToString(CultureInfo.InvariantCulture));
                    for (int c = 0; c < filasHoja[i].Count; c++)
                        if (!string.IsNullOrEmpty(filasHoja[i][c])) meta.Set(fila, 3 + c, filasHoja[i][c]);
                    fila++;
                }
            }

            ExcelXlsx.Escribir(Recursos.Plantilla(), hoja1, hoja2, orden, meta, destino);

            // Foto en la carpeta compartida (solo modelos de VENTAS): el reporte la usa como referencia, aunque
            // alguien edite el Excel (incluida la hoja oculta).
            if (!string.IsNullOrWhiteSpace(cfg.carpeta_5d) && modelo.EsDeVentas(cfg))
            {
                var foto = new Dictionary<string, object>
                {
                    ["info"] = info,
                    ["destino"] = destino,
                    ["contenido"] = contenido,
                    ["tablas_5d"] = originales5D
                };
                var ruta = Path.Combine(cfg.carpeta_5d, "exportaciones", ahora.ToString("yyyy-MM", CultureInfo.InvariantCulture),
                    "urn_" + Usuario.Archivo(modelo.Linaje) + "__" + ahora.ToString("yyyyMMdd_HHmmss", CultureInfo.InvariantCulture) + "__" + exportId + ".json");
                Json.GuardarAtomico(ruta, foto);
            }
            return exportId;
        }

        static List<List<string>> Filas(Hoja h, int desde)
        {
            var salida = new List<List<string>>();
            for (int r = desde; r <= h.Celdas.Count; r++)
            {
                var f = h.Celdas[r - 1].Select(Hoja.Texto).ToList();
                while (f.Count > 0 && f[f.Count - 1].Length == 0) f.RemoveAt(f.Count - 1);
                salida.Add(f);
            }
            while (salida.Count > 0 && salida[salida.Count - 1].Count == 0) salida.RemoveAt(salida.Count - 1);
            return salida;
        }

        // "Frente de trabajo" (lo pedia la macro de Hoja2). Opciones: los valores de la tabla FRENTES del
        // modelo, si existe (sin DESCARTADO); se puede escribir otro. null = cancelado.
        static string PedirFrente(List<Tabla> tablas)
        {
            var opciones = tablas.Where(t => string.Equals(t.nombre?.Trim(), "FRENTES", StringComparison.OrdinalIgnoreCase))
                .SelectMany(t => t.filas.Skip(1)).Select(f => f.FirstOrDefault()?.Trim() ?? "")
                .Where(v => v.Length > 0 && !v.Equals("DESCARTADO", StringComparison.OrdinalIgnoreCase))
                .Distinct().ToList();

            using var form = new WinForm
            {
                Text = "Exportar Presupuesto",
                Width = 420, Height = 175,
                StartPosition = System.Windows.Forms.FormStartPosition.CenterScreen,
                FormBorderStyle = System.Windows.Forms.FormBorderStyle.FixedDialog,
                MaximizeBox = false, MinimizeBox = false, TopMost = true
            };
            var lbl = new WinLabel { Text = "Frente de trabajo:", Left = 15, Top = 18, Width = 380 };
            var combo = new WinCombo { Left = 15, Top = 42, Width = 375, DropDownStyle = System.Windows.Forms.ComboBoxStyle.DropDown };
            combo.Items.AddRange(opciones.Cast<object>().ToArray());
            if (opciones.Count > 0) combo.SelectedIndex = 0;
            var ok = new WinButton { Text = "Exportar", Left = 215, Top = 85, Width = 85, DialogResult = WinResult.OK };
            var cancel = new WinButton { Text = "Cancelar", Left = 305, Top = 85, Width = 85, DialogResult = WinResult.Cancel };
            form.Controls.AddRange(new System.Windows.Forms.Control[] { lbl, combo, ok, cancel });
            form.AcceptButton = ok; form.CancelButton = cancel;
            return form.ShowDialog() == WinResult.OK ? (combo.Text ?? "").Trim() : null;
        }

        static string PedirRuta(string nombre)
        {
            using var dlg = new System.Windows.Forms.SaveFileDialog
            {
                Title = "Guardar presupuesto", FileName = nombre, Filter = "Excel (*.xlsx)|*.xlsx", OverwritePrompt = true
            };
            return dlg.ShowDialog() == WinResult.OK ? dlg.FileName : null;
        }

        // Carpeta 02121_CATALOGOS del proyecto del modelo, en Desktop Connector:
        //   1) proyecto segun _modelos_ventas.json (lo escribe el reporte 5D con el catalogo de ACC, por URN);
        //   2) %USERPROFILE%\DC\ACCDocs\<hub>\VENTAS GCP\Project Files\<proyecto>\<ruta_catalogos>.
        // Si algo falla, null (se pregunta donde guardar).
        internal static string ResolverCarpeta(Config cfg, Modelo modelo)
        {
            try
            {
                if (modelo.ItemId == null || string.IsNullOrWhiteSpace(cfg.carpeta_5d)) return null;
                var mapa = Path.Combine(cfg.carpeta_5d, "_modelos_ventas.json");
                if (!File.Exists(mapa)) return null;
                using var j = JsonDocument.Parse(File.ReadAllText(mapa));
                if (!j.RootElement.TryGetProperty("modelos", out var modelos) ||
                    !modelos.TryGetProperty(modelo.ItemId, out var m) ||
                    !m.TryGetProperty("proyecto", out var proy)) return null;
                var proyecto = proy.GetString();
                var acc = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "DC", "ACCDocs");
                var raiz = Directory.Exists(acc)
                    ? Directory.GetDirectories(acc).Select(h => Path.Combine(h, cfg.proyecto_acc)).FirstOrDefault(Directory.Exists)
                    : null;
                if (raiz == null) return null;
                var archivos = Directory.GetDirectories(raiz).FirstOrDefault(d =>
                    new[] { "Project Files", "Archivos de proyecto" }.Contains(Path.GetFileName(d), StringComparer.OrdinalIgnoreCase));
                if (archivos == null) return null;
                var carpeta = Path.Combine(archivos, proyecto, cfg.ruta_catalogos);
                Directory.CreateDirectory(carpeta);
                return carpeta;
            }
            catch (Exception ex)
            {
                Log.Escribir("No se pudo ubicar 02121_CATALOGOS: " + ex.Message);
                return null;
            }
        }
    }

    internal static class Recursos
    {
        public static byte[] Plantilla() => Leer("Plantilla_Presupuesto_5D.xlsx");

        public static byte[] Leer(string nombre)
        {
            var asm = typeof(Recursos).Assembly;
            var res = asm.GetManifestResourceNames().FirstOrDefault(n => n.EndsWith(nombre, StringComparison.OrdinalIgnoreCase))
                      ?? throw new FileNotFoundException("Recurso no incluido en el add-in: " + nombre);
            using var s = asm.GetManifestResourceStream(res);
            using var ms = new MemoryStream();
            s.CopyTo(ms);
            return ms.ToArray();
        }
    }
}
