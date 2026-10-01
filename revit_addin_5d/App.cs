// App.cs -- Sync5D (5D_VENTAS): 4o add-in de Revit, independiente de SheetSync, RevitSyncLogger y AuditSync.
//
//  - Pestana "5D" con el boton "Exportar Presupuesto" (ExportarPresupuesto.cs).
//  - Al sincronizar un modelo del proyecto VENTAS GCP corre los MODULOS 5D y guarda su resultado en
//    03374_5D_VENTAS\resultados\<AAAA-MM>\urn_<modelo>__<PC>_<usuario>.json (uno por modelo, mes y persona):
//      base_datos : conceptos de Revit contra la Base de Datos de Presupuestos (Catalogo5D.cs)
//      tablas     : foto de las tablas 5D (000-999), para saber si el ultimo Excel exportado sigue vigente
//    Para agregar una metrica 5D nueva: otra entrada en Modulos (id + funcion) y su pestana en el reporte.
//  - Sin ventanas al sincronizar; cualquier error va a %LOCALAPPDATA%\Sync5D\sync5d.log.
//
// Requiere .NET SDK 8 y Revit 2025. Compilar con compilar.bat.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Windows.Media.Imaging;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Events;
using Autodesk.Revit.UI;

namespace Ventas5D.Sync5D
{
    public class App : IExternalApplication
    {
        // Modulos que corren al sincronizar: id -> funcion que devuelve el resultado (se guarda como JSON).
        static readonly List<(string id, Func<Document, Config, object> correr)> Modulos =
            new List<(string, Func<Document, Config, object>)>
            {
                ("base_datos", (doc, cfg) =>
                {
                    var sw = Stopwatch.StartNew();
                    var catalogo = Catalogo5D.Cargar(cfg.carpeta_5d, out var archivo);
                    var r = Revision5D.Correr(doc, catalogo);
                    r.fecha = DateTimeOffset.Now.ToString("o");
                    r.duracion_s = Math.Round(sw.Elapsed.TotalSeconds, 2);
                    r.catalogo = archivo;
                    return r;
                }),
                ("tablas", (doc, cfg) =>
                {
                    var sw = Stopwatch.StartNew();
                    var f = new FotoTablas { tablas = Tablas5D.Leer(doc, true) };
                    f.fecha = DateTimeOffset.Now.ToString("o");
                    f.duracion_s = Math.Round(sw.Elapsed.TotalSeconds, 2);
                    return f;
                }),
            };

        public Result OnStartup(UIControlledApplication app)
        {
            try { CrearCinta(app); }
            catch (Exception ex) { Log.Escribir("ERROR cinta " + ex); }
            app.ControlledApplication.DocumentSynchronizedWithCentral += AlSincronizar;
            return Result.Succeeded;
        }

        public Result OnShutdown(UIControlledApplication app)
        {
            app.ControlledApplication.DocumentSynchronizedWithCentral -= AlSincronizar;
            return Result.Succeeded;
        }

        static void CrearCinta(UIControlledApplication app)
        {
            const string pestana = "5D";
            try { app.CreateRibbonTab(pestana); } catch (Autodesk.Revit.Exceptions.ArgumentException) { /* ya existe */ }
            var panel = app.GetRibbonPanels(pestana).FirstOrDefault(p => p.Name == "Presupuesto")
                        ?? app.CreateRibbonPanel(pestana, "Presupuesto");
            var datos = new PushButtonData("Sync5D_ExportarPresupuesto", "Exportar\nPresupuesto",
                typeof(App).Assembly.Location, typeof(ExportarPresupuesto).FullName)
            {
                ToolTip = "Genera el Excel del presupuesto (una pestana por tabla, Hoja1 y Hoja2 compiladas) " +
                          "y lo guarda en 02121_CATALOGOS del proyecto.",
                LargeImage = Imagen("exportar_32.png"),
                Image = Imagen("exportar_16.png")
            };
            panel.AddItem(datos);
        }

        static BitmapSource Imagen(string nombre)
        {
            try
            {
                var bytes = Recursos.Leer(nombre);
                var img = new BitmapImage();
                img.BeginInit();
                img.StreamSource = new MemoryStream(bytes);
                img.CacheOption = BitmapCacheOption.OnLoad;
                img.EndInit();
                img.Freeze();
                return img;
            }
            catch { return null; }
        }

        void AlSincronizar(object sender, DocumentSynchronizedWithCentralEventArgs e)
        {
            try
            {
                if (e.Status != RevitAPIEventStatus.Succeeded) return;
                var doc = e.Document;
                if (doc == null || doc.IsFamilyDocument || !doc.IsModelInCloud) return;
                var cfg = Config.Leer();
                if (cfg == null || string.IsNullOrWhiteSpace(cfg.carpeta_5d)) return;
                var modelo = Modelo.De(doc);
                if (!modelo.EsDeVentas(cfg)) return;   // solo VENTAS GCP

                var ahora = DateTimeOffset.Now;
                var ruta = Path.Combine(cfg.carpeta_5d, "resultados", ahora.ToString("yyyy-MM", CultureInfo.InvariantCulture),
                    "urn_" + Usuario.Archivo(modelo.Linaje) + "__" + Usuario.Archivo(Usuario.Maquina + "_" + Usuario.Windows) + ".json");
                var reg = RegistroSync.Leer(ruta) ?? new RegistroSync { primera_sync = ahora.ToString("o") };
                reg.modelo = modelo.Titulo;
                reg.model_urn = modelo.ModelUrn;
                reg.project_id = modelo.ProjectId;
                reg.hub_id = modelo.HubId;
                reg.revit_user = doc.Application.Username ?? "";
                reg.windows_user = Usuario.Windows;
                reg.maquina = Usuario.Maquina;
                reg.revit_version = doc.Application.VersionNumber ?? "";
                reg.syncs += 1;
                reg.ultima_sync = ahora.ToString("o");

                foreach (var (id, correr) in Modulos)
                {
                    try { reg.Poner(id, correr(doc, cfg)); }
                    catch (Exception ex) { Log.Escribir($"ERROR modulo {id} en {modelo.Titulo}: {ex.Message}"); }
                }
                Json.GuardarAtomico(ruta, reg);
                Log.Escribir($"OK {modelo.Titulo}: {reg.modulos.Count} modulos");
            }
            catch (Exception ex)
            {
                Log.Escribir("ERROR " + ex);
            }
        }
    }
}
