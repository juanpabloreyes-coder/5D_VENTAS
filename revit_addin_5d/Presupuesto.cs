// Presupuesto.cs -- Sync5D: compilado de Hoja1 y Hoja2, igual que las macros de la plantilla Catalogo.xlsm
// del GCP_PLUGIN, ahora hecho por el boton (el Excel sale sin macros ni botones):
//   - Hoja1: "ReorganizarExtraerYConsolidarSinFilaVacia" (boton de Excel "Generar Presupuesto")
//   - Hoja2: "PresupuestoBase"                          (boton de Excel "EXTRAER CONCEPTOS BASE")
// Diferencia acordada: solo se compilan pestanas cuyo nombre empieza con 3 digitos (000-999); la macro de
// Hoja2 tomaba todas (P-01.x, ACAB..., FRENTES) y metia filas que no son conceptos.
// Las pestanas quedan como las deja la macro (columna de partida eliminada, titulo en C2, columnas extra
// transpuestas y unidad separada del parentesis).

using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.RegularExpressions;

namespace Ventas5D.Sync5D
{
    // Una hoja en memoria. Celdas 1-based; valor string o double (como Excel guarda lo que escribe una macro).
    internal sealed class Hoja
    {
        public string Nombre;
        public List<List<object>> Celdas = new List<List<object>>();
        public HashSet<string> Negritas = new HashSet<string>();   // "fila,columna"
        public bool Oculta;

        public Hoja(string nombre) { Nombre = nombre; }

        public object Get(int r, int c) =>
            r >= 1 && r <= Celdas.Count && c >= 1 && c <= Celdas[r - 1].Count ? Celdas[r - 1][c - 1] : null;

        public string Txt(int r, int c) => Texto(Get(r, c));

        public void Set(int r, int c, object v)
        {
            while (Celdas.Count < r) Celdas.Add(new List<object>());
            var f = Celdas[r - 1];
            while (f.Count < c) f.Add(null);
            f[c - 1] = v;
        }

        public void Negrita(int r, int c) => Negritas.Add(r + "," + c);
        public bool EsNegrita(int r, int c) => Negritas.Contains(r + "," + c);

        public void InsertarFila(int r)   // nueva fila vacia en la posicion r (desplaza hacia abajo)
        {
            while (Celdas.Count < r - 1) Celdas.Add(new List<object>());
            Celdas.Insert(r - 1, new List<object>());
            Negritas = new HashSet<string>(Negritas.Select(k =>
            {
                var p = k.Split(','); var fr = int.Parse(p[0]);
                return (fr >= r ? fr + 1 : fr) + "," + p[1];
            }));
        }

        public void BorrarColumnaA()
        {
            foreach (var f in Celdas) if (f.Count > 0) f.RemoveAt(0);
            Negritas = new HashSet<string>(Negritas.Select(k => k.Split(',')).Where(p => p[1] != "1")
                .Select(p => p[0] + "," + (int.Parse(p[1]) - 1)));
        }

        // .Cells(.Rows.Count, col).End(xlUp).Row
        public int UltimaFilaCol(int c)
        {
            for (int r = Celdas.Count; r >= 1; r--) if (!Vacia(Get(r, c))) return r;
            return 1;
        }

        // .Cells(r, .Columns.Count).End(xlToLeft).Column
        public int UltimaColFila(int r)
        {
            if (r < 1 || r > Celdas.Count) return 1;
            for (int c = Celdas[r - 1].Count; c >= 1; c--) if (!Vacia(Get(r, c))) return c;
            return 1;
        }

        // .UsedRange.Rows.Count (la plantilla y las pestanas empiezan en la fila 1)
        public int FilasUsadas()
        {
            for (int r = Celdas.Count; r >= 1; r--)
                if (Celdas[r - 1].Any(v => !Vacia(v))) return r;
            return 1;
        }

        public static bool Vacia(object v) => v == null || (v is string s && s.Length == 0);
        public static string Texto(object v) =>
            v == null ? "" : v is double d ? d.ToString("R", CultureInfo.InvariantCulture) : v.ToString();

        // IsNumeric de VBA (vacio cuenta como numerico)
        public static bool EsNumero(object v)
        {
            if (Vacia(v) || v is double) return true;
            return double.TryParse(Texto(v).Trim(), NumberStyles.Any, CultureInfo.InvariantCulture, out _);
        }

        // Lo que hace Excel al recibir un texto en una celda General: si parece numero, lo guarda como numero.
        public static object ComoExcel(object v)
        {
            if (v is string s)
            {
                var t = s.Trim();
                if (t.Length > 0 && Regex.IsMatch(t, @"^-?\d+(\.\d+)?$") &&
                    double.TryParse(t, NumberStyles.Float, CultureInfo.InvariantCulture, out var d))
                    return d;
            }
            return v;
        }
    }

    internal static class Presupuesto
    {
        static readonly string[] UnidadesPermitidas = { "ml", "m2", "pza", "m3", "lote", "kg" };
        static readonly StringComparer OrdenMacro1 = StringComparer.Create(new CultureInfo("es-MX"), false); // ArrayList.Sort
        static readonly StringComparer OrdenMacro2 = StringComparer.Ordinal;                                  // comparacion binaria de VBA

        // tablas: todas las tablas exportadas (en el orden del libro). hoja1/hoja2: hojas de la plantilla.
        // Devuelve el orden final de las pestanas de tablas (como queda despues de la macro).
        public static List<Hoja> Compilar(List<Hoja> tablas, Hoja hoja1, Hoja hoja2, string frente)
        {
            var de5D = tablas.Where(h => Tablas5D.EsDe5D(h.Nombre)).ToList();

            // ---- Hoja1 (SinFilaVacia): orden de pestanas: las 000-999 al final, ordenadas
            var ordenadas = de5D.Select(h => h.Nombre).OrderBy(n => n, OrdenMacro1).ToList();
            var orden = tablas.Where(h => !Tablas5D.EsDe5D(h.Nombre)).ToList();
            orden.AddRange(ordenadas.Select(n => de5D.First(h => h.Nombre == n)));

            // Titulos: si hay codigo en B, la partida (A2 o A3) pasa a C2 en negritas y se borra la columna A
            foreach (var ws in de5D)
            {
                var lr = ws.UltimaFilaCol(2);
                var tiene = false;
                for (int i = 3; i <= lr; i++) if (Hoja.EsNumero(ws.Get(i, 2))) { tiene = true; break; }
                if (!tiene) continue;
                var titulo = !Hoja.Vacia(ws.Get(2, 1)) ? ws.Get(2, 1) : !Hoja.Vacia(ws.Get(3, 1)) ? ws.Get(3, 1) : "";
                ws.BorrarColumnaA();
                if (!Hoja.Vacia(titulo)) { ws.Set(2, 3, titulo); ws.Negrita(2, 3); }
            }

            // Transposicion: columnas 5 en adelante pasan a filas debajo (encabezado en B, valor en D)
            foreach (var n in ordenadas)
            {
                var ws = de5D.First(h => h.Nombre == n);
                for (int r = ws.FilasUsadas(); r >= 2; r--)
                {
                    for (int c = ws.UltimaColFila(r); c >= 5; c--)
                    {
                        var v = ws.Get(r, c);
                        if (Hoja.Vacia(v)) continue;
                        ws.InsertarFila(r + 1);
                        ws.Set(r + 1, 4, Hoja.ComoExcel(v));
                        ws.Set(r + 1, 2, ws.Get(1, c));
                        ws.Set(r, c, null);
                    }
                }
            }

            // Unidad entre parentesis -> columna C (solo unidades permitidas, como la macro)
            foreach (var n in ordenadas)
            {
                var ws = de5D.First(h => h.Nombre == n);
                for (int r = 2; r <= ws.FilasUsadas(); r++)
                {
                    if (!Hoja.Vacia(ws.Get(r, 3))) continue;
                    var b = Hoja.Texto(ws.Get(r, 2));
                    var m = Regex.Match(b, @"\((.*?)\)");
                    if (!m.Success) continue;
                    var u = m.Groups[1].Value;
                    if (!UnidadesPermitidas.Contains(u)) continue;   // sensible a mayusculas, como la macro
                    ws.Set(r, 3, u);
                    ws.Set(r, 2, b.Replace(" (" + u + ")", "").Trim());
                }
            }

            // Consolidado en Hoja1
            hoja1.Set(10, 1, "01");
            int fila = 11, partida = 101; var primerTitulo = true;
            foreach (var n in ordenadas)
            {
                var ws = de5D.First(h => h.Nombre == n);
                var lr = ws.FilasUsadas();
                if (lr < 2) continue;
                if (ws.EsNegrita(2, 3))
                {
                    if (primerTitulo) { hoja1.Set(fila, 1, "01.0101"); primerTitulo = false; }
                    else { partida++; hoja1.Set(fila, 1, "01." + partida.ToString("0000")); }
                    hoja1.Set(fila, 3, ws.Get(2, 3)); hoja1.Negrita(fila, 3);
                    fila++;
                }
                object ultimoCodigo = "";
                for (int r = 3; r <= lr; r++)
                {
                    if (!Hoja.Vacia(ws.Get(r, 1))) ultimoCodigo = ws.Get(r, 1);
                    hoja1.Set(fila, 1, "01." + partida.ToString("0000"));
                    hoja1.Set(fila, 2, Hoja.ComoExcel(ultimoCodigo));
                    hoja1.Set(fila, 3, Hoja.ComoExcel(ws.Get(r, 2)));
                    hoja1.Set(fila, 4, Hoja.ComoExcel(ws.Get(r, 3)));
                    hoja1.Set(fila, 5, Hoja.ComoExcel(ws.Get(r, 4)));
                    fila++;
                }
            }

            // ---- Hoja2 (PresupuestoBase), solo pestanas 000-999
            int destino = 11, seccion = 101; var codigo = "01";
            foreach (var n in de5D.Select(h => h.Nombre).OrderBy(x => x, OrdenMacro2))
            {
                var ws = de5D.First(h => h.Nombre == n);
                var titulo = Hoja.Texto(ws.Get(2, 3)).Trim();
                if (titulo.Length > 0)
                {
                    codigo = "01.01" + ("0" + (seccion - 100)).Substring(("0" + (seccion - 100)).Length - 2);
                    seccion++;
                    hoja2.Set(destino, 1, codigo); hoja2.Negrita(destino, 1);
                    hoja2.Set(destino, 3, titulo); hoja2.Negrita(destino, 3);
                    destino++;
                }
                var lr = ws.UltimaFilaCol(1);
                for (int r = 3; r <= lr; r++)
                {
                    if (Hoja.Texto(ws.Get(r, 1)).Trim().Length == 0) continue;
                    hoja2.Set(destino, 1, codigo);
                    for (int k = 1; k <= 4; k++) hoja2.Set(destino, k + 1, Hoja.ComoExcel(ws.Get(r, k)));
                    destino++;
                }
            }
            if (!string.IsNullOrWhiteSpace(frente)) hoja2.Set(10, 3, frente);
            hoja2.Set(10, 1, "01"); hoja2.Negrita(10, 1);
            return orden;
        }
    }
}
