// OcultarGcp.cs -- Sync5D (5D_VENTAS): oculta el boton viejo "Exportar Presupuesto" de la pestana GCPEASA
// (GCP_PLUGIN, sin codigo fuente) para que solo quede el boton nuevo de la pestana 5D.
//  - Solo lo OCULTA en la cinta; GCP_PLUGIN sigue instalado y el resto de su pestana queda igual.
//  - Si la PC no tiene GCP_PLUGIN, no hace nada.
//  - Para volver a mostrarlo: "ocultar_exportar_gcp": false en sync5d-config.json (junto al .dll) y reabrir Revit.

using System;
using System.Collections.Generic;
using Autodesk.Windows;

namespace Ventas5D.Sync5D
{
    internal static class OcultarGcp
    {
        const string PestanaGcp = "GCPEASA";

        public static int Ocultar()
        {
            int n = 0;
            var ribbon = ComponentManager.Ribbon;
            if (ribbon == null) return 0;
            foreach (var tab in ribbon.Tabs)
            {
                if (tab == null) continue;
                var titulo = (tab.Title ?? tab.Id ?? "").Trim();
                if (!titulo.Equals(PestanaGcp, StringComparison.OrdinalIgnoreCase)) continue;
                foreach (var panel in tab.Panels)
                {
                    if (panel?.Source == null) continue;
                    foreach (var it in Recorrer(panel.Source.Items))
                    {
                        var txt = Norm(it.Text) + " " + Norm(it.Name) + " " + Norm(it.Id);
                        if (txt.Contains("EXPORTAR") && txt.Contains("PRESUPUESTO") && it.IsVisible)
                        {
                            it.IsVisible = false;
                            n++;
                        }
                    }
                }
            }
            return n;
        }

        static IEnumerable<RibbonItem> Recorrer(IEnumerable<RibbonItem> items)
        {
            if (items == null) yield break;
            foreach (var i in items)
            {
                if (i == null) continue;
                yield return i;
                if (i is RibbonRowPanel fila)
                    foreach (var x in Recorrer(fila.Items)) yield return x;
                if (i is RibbonListButton lista)
                    foreach (var x in Recorrer(lista.Items)) yield return x;
            }
        }

        static string Norm(string s) => (s ?? "").Replace("\r", " ").Replace("\n", " ").ToUpperInvariant();
    }
}
