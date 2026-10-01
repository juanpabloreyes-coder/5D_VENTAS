// Comun.cs -- Sync5D (5D_VENTAS): configuracion, bitacora, identidad del modelo y archivos compartidos.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Principal;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Serialization;
using Autodesk.Revit.DB;

namespace Ventas5D.Sync5D
{
    // sync5d-config.json junto al .dll (lo escribe Instalador\instalar.ps1).
    internal sealed class Config
    {
        // Carpeta compartida 0337_SQDCM\03374_5D_VENTAS: catalogo PPTO MAESTRO (.csv), resultados al
        // sincronizar (resultados\AAAA-MM) y fotos de cada exportacion (exportaciones\AAAA-MM).
        public string carpeta_5d { get; set; }
        // Proyecto VENTAS GCP en ACC: solo esos modelos se revisan.
        public string project_id { get; set; }
        // Subcarpeta del proyecto donde se guarda el Excel de presupuesto.
        public string ruta_catalogos { get; set; } = @"02_PRESUPUESTOS\021_AUXILIARES\0212_CUANTIFICACIONES\02121_CATALOGOS";
        // Nombre de la carpeta del proyecto de ACC en Desktop Connector.
        public string proyecto_acc { get; set; } = "VENTAS GCP";

        public static Config Leer()
        {
            try
            {
                var p = Path.Combine(Path.GetDirectoryName(typeof(Config).Assembly.Location) ?? "", "sync5d-config.json");
                return File.Exists(p) ? JsonSerializer.Deserialize<Config>(File.ReadAllText(p)) : null;
            }
            catch { return null; }
        }
    }

    internal static class Log
    {
        public static void Escribir(string msg)
        {
            try
            {
                var dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Sync5D");
                Directory.CreateDirectory(dir);
                File.AppendAllText(Path.Combine(dir, "sync5d.log"), $"{DateTime.Now:yyyy-MM-dd HH:mm:ss}  {msg}{Environment.NewLine}");
            }
            catch { }
            // Copia junto al add-in (carpeta Addins\2025) para poder revisarla facilmente
            try
            {
                var dir2 = Path.GetDirectoryName(typeof(Log).Assembly.Location);
                if (!string.IsNullOrEmpty(dir2))
                    File.AppendAllText(Path.Combine(dir2, "Sync5D.log"), $"{DateTime.Now:yyyy-MM-dd HH:mm:ss}  {msg}{Environment.NewLine}");
            }
            catch { }
        }
    }

    internal static class Json
    {
        public static readonly JsonSerializerOptions Opciones = new JsonSerializerOptions
        {
            Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
            DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull
        };

        public static void GuardarAtomico(string ruta, object obj)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(ruta));
            var tmp = ruta + ".tmp";
            for (var i = 0; i < 3; i++)
            {
                try
                {
                    File.WriteAllText(tmp, JsonSerializer.Serialize(obj, Opciones), new UTF8Encoding(false));
                    File.Copy(tmp, ruta, true);
                    File.Delete(tmp);
                    return;
                }
                catch (IOException) when (i < 2) { System.Threading.Thread.Sleep(300); }
            }
        }
    }

    // Identidad del modelo en ACC (por reflexion, como SheetSync / RevitSyncLogger / AuditSync).
    internal sealed class Modelo
    {
        public string Titulo, ModelUrn, ProjectId, HubId, Linaje;

        public static Modelo De(Document doc)
        {
            var m = new Modelo
            {
                Titulo = doc.Title ?? "",
                ModelUrn = Get(doc, "GetCloudModelUrn"),
                ProjectId = Get(doc, "GetProjectId"),
                HubId = Get(doc, "GetHubId")
            };
            m.Linaje = IdLinaje(m.ModelUrn);
            return m;
        }

        public bool EsDeVentas(Config cfg) =>
            Linaje != null && (string.IsNullOrWhiteSpace(cfg.project_id) || SinB(ProjectId) == SinB(cfg.project_id));

        public string ItemId => Linaje == null ? null : "urn:adsk.wipprod:dm.lineage:" + Linaje;

        static string Get(Document d, string metodo)
        {
            try { return d.GetType().GetMethod(metodo, BindingFlags.Instance | BindingFlags.Public)?.Invoke(d, null)?.ToString() ?? ""; }
            catch { return ""; }
        }

        public static string SinB(string id)
        {
            id = (id ?? "").Trim().ToLowerInvariant();
            return id.StartsWith("b.") ? id.Substring(2) : id;
        }

        static string IdLinaje(string urn)
        {
            if (string.IsNullOrEmpty(urn)) return null;
            var i = urn.IndexOf("dm.lineage:", StringComparison.OrdinalIgnoreCase);
            if (i < 0) return null;
            var id = urn.Substring(i + "dm.lineage:".Length);
            var q = id.IndexOf('?');
            if (q >= 0) id = id.Substring(0, q);
            return id.Length > 0 ? id : null;
        }
    }

    internal static class Usuario
    {
        public static string Windows => WindowsIdentity.GetCurrent()?.Name ?? Environment.UserName;
        public static string Maquina => Environment.MachineName;

        public static string Archivo(string s)
        {
            foreach (var c in Path.GetInvalidFileNameChars()) s = s.Replace(c, '_');
            return s.Replace(' ', '_');
        }
    }

    // Archivo por modelo + mes + maquina/usuario con lo que corrio al sincronizar (mismo esquema que AuditSync).
    internal sealed class RegistroSync
    {
        public int version_formato { get; set; } = 1;
        public string modelo { get; set; }
        public string model_urn { get; set; }
        public string project_id { get; set; }
        public string hub_id { get; set; }
        public string revit_user { get; set; }
        public string windows_user { get; set; }
        public string maquina { get; set; }
        public string revit_version { get; set; }
        public int syncs { get; set; }
        public string primera_sync { get; set; }
        public string ultima_sync { get; set; }
        // Un resultado por modulo: "base_datos", "tablas", ... (abierto a modulos nuevos)
        public Dictionary<string, JsonElement> modulos { get; set; } = new Dictionary<string, JsonElement>();

        public static RegistroSync Leer(string ruta)
        {
            try { return File.Exists(ruta) ? JsonSerializer.Deserialize<RegistroSync>(File.ReadAllText(ruta), Json.Opciones) : null; }
            catch { return null; }
        }

        public void Poner(string modulo, object resultado) =>
            modulos[modulo] = JsonSerializer.SerializeToElement(resultado, Json.Opciones);
    }
}
