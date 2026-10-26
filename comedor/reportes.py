"""Reportes del comedor. Cada función devuelve un `Reporte` que la interfaz muestra,
exporta a CSV o imprime."""
import csv
import locale
from dataclasses import dataclass, field

from . import inventario, personal, raciones, ventas
from .util import fecha_ver, fmt_cant, fmt_dinero, formatear, r2


@dataclass
class Reporte:
    titulo: str
    columnas: list                      # [(titulo, tipo, ancho)]; tipo: texto, dinero, cant, entero, fecha, pct
    filas: list = field(default_factory=list)
    totales: list = None
    subtitulo: str = ""
    resumen: list = field(default_factory=list)   # [(etiqueta, texto)]

    def filas_formateadas(self):
        tipos = [c[1] for c in self.columnas]
        return [[formatear(v, t) for v, t in zip(fila, tipos)] for fila in self.filas]

    def totales_formateados(self):
        if not self.totales:
            return None
        return [formatear(v, c[1]) for v, c in zip(self.totales, self.columnas)]


def _periodo(desde, hasta):
    return fecha_ver(desde) if desde == hasta else f"Del {fecha_ver(desde)} al {fecha_ver(hasta)}"


def _uno(con, sql, parametros):
    return con.execute(sql, parametros).fetchone()[0] or 0


# --- Reportes del catálogo ---------------------------------------------------------

def resumen_general(con, desde, hasta, unidad=""):
    p = (desde, hasta)
    filas = []
    for t in raciones.tiempos(con):
        n, v = con.execute(
            "SELECT COUNT(*), COALESCE(SUM(precio), 0) FROM raciones WHERE tiempo_id = ? AND fecha BETWEEN ? AND ?",
            (t["id"],) + p,
        ).fetchone()
        filas.append([f"Raciones institucionales – {t['nombre']}", n, r2(v)])
    for forma, nombre in ventas.FORMAS_PAGO.items():
        n, v = con.execute(
            """SELECT COUNT(*), COALESCE(SUM(total), 0) FROM ventas
               WHERE forma_pago = ? AND anulada = 0 AND fecha BETWEEN ? AND ?""",
            (forma,) + p,
        ).fetchone()
        filas.append([f"Ventas de {nombre.lower()}", n, r2(v)])
    n, v = con.execute("SELECT COUNT(*), COALESCE(SUM(monto), 0) FROM cobros WHERE fecha BETWEEN ? AND ?", p).fetchone()
    filas.append(["Cobros de crédito recibidos", n, r2(v)])
    n, v = con.execute("SELECT COUNT(*), COALESCE(SUM(total), 0) FROM compras WHERE fecha BETWEEN ? AND ?", p).fetchone()
    filas.append(["Compras de insumos", n, r2(v)])
    for origen, nombre in inventario.ORIGENES_SALIDA.items():
        v = _uno(con, "SELECT SUM(-cantidad * costo_unit) FROM movimientos WHERE origen = ? AND fecha BETWEEN ? AND ?",
                 (origen,) + p)
        filas.append([f"Salidas de bodega – {nombre} (al costo)", "", r2(v)])
    anuladas = _uno(con, "SELECT COUNT(*) FROM ventas WHERE anulada = 1 AND fecha BETWEEN ? AND ?", p)
    efectivo = r2(sum(f[2] for f in filas if f[0] in ("Ventas de contado", "Cobros de crédito recibidos")))
    return Reporte(
        "Resumen general",
        [("Concepto", "texto", 380), ("Cantidad", "entero", 90), ("Valor", "dinero", 120)],
        filas,
        subtitulo=_periodo(desde, hasta),
        resumen=[("Efectivo que debe haber ingresado (contado + cobros)", fmt_dinero(efectivo)),
                 ("Ventas anuladas en el período", str(anuladas))],
    )


def liquidacion_raciones(con, desde, hasta, unidad=""):
    ts = raciones.tiempos(con)
    columnas_t = ", ".join(f"SUM(r.tiempo_id = {int(t['id'])}) AS t{int(t['id'])}" for t in ts)
    sql = f"""SELECT p.cedula, p.grado, p.nombres, p.unidad, {columnas_t}, COUNT(*) AS n, SUM(r.precio) AS valor
              FROM raciones r JOIN personal p ON p.id = r.personal_id
              WHERE r.fecha BETWEEN ? AND ?"""
    parametros = [desde, hasta]
    if unidad:
        sql += " AND p.unidad = ?"
        parametros.append(unidad)
    filas_db = con.execute(sql + " GROUP BY p.id ORDER BY p.unidad, p.nombres", parametros).fetchall()
    filas = [[f["cedula"], f["grado"], f["nombres"], f["unidad"]] + [f[f"t{t['id']}"] for t in ts]
             + [f["n"], r2(f["valor"])] for f in filas_db]
    nt = len(ts)
    totales = ["", "", f"TOTAL ({len(filas)} personas)", ""] + [sum(f[4 + i] for f in filas) for i in range(nt)] \
        + [sum(f[4 + nt] for f in filas), r2(sum(f[-1] for f in filas))]

    sql_t = "SELECT r.tiempo_id, COUNT(*), SUM(r.precio) FROM raciones r JOIN personal p ON p.id = r.personal_id " \
            "WHERE r.fecha BETWEEN ? AND ?" + (" AND p.unidad = ?" if unidad else "") + " GROUP BY r.tiempo_id"
    por_tiempo = {tid: (n, v) for tid, n, v in con.execute(sql_t, parametros)}
    resumen = [(f"{t['nombre']}: {por_tiempo.get(t['id'], (0, 0))[0]} raciones",
                fmt_dinero(por_tiempo.get(t["id"], (0, 0))[1])) for t in ts]
    resumen.append(("TOTAL A FACTURAR A LA INSTITUCIÓN", fmt_dinero(totales[-1])))
    return Reporte(
        "Liquidación de raciones institucionales",
        [("Cédula", "texto", 100), ("Grado", "texto", 120), ("Apellidos y nombres", "texto", 240),
         ("Unidad", "texto", 140)] + [(t["nombre"], "entero", 80) for t in ts]
        + [("Total raciones", "entero", 90), ("Valor", "dinero", 100)],
        filas, totales,
        subtitulo=_periodo(desde, hasta) + (f" · Unidad: {unidad}" if unidad else ""),
        resumen=resumen,
    )


def ventas_por_dia(con, desde, hasta, unidad=""):
    filas = [list(f) for f in con.execute(
        """SELECT fecha, COUNT(*),
                  SUM(CASE WHEN forma_pago = 'CONTADO' THEN total ELSE 0 END),
                  SUM(CASE WHEN forma_pago = 'CREDITO' THEN total ELSE 0 END),
                  SUM(subtotal_0), SUM(base_iva), SUM(iva), SUM(total)
           FROM ventas WHERE anulada = 0 AND fecha BETWEEN ? AND ? GROUP BY fecha ORDER BY fecha""",
        (desde, hasta),
    )]
    totales = ["TOTAL"] + [sum(f[i] for f in filas) for i in range(1, 8)]
    return Reporte(
        "Ventas por día",
        [("Fecha", "fecha", 90), ("N° ventas", "entero", 80), ("Contado", "dinero", 100), ("Crédito", "dinero", 100),
         ("Subtotal 0%", "dinero", 100), ("Base IVA", "dinero", 100), ("IVA", "dinero", 90), ("Total", "dinero", 110)],
        filas, totales, subtitulo=_periodo(desde, hasta),
    )


def detalle_ventas(con, desde, hasta, unidad=""):
    filas = []
    for v in reversed(ventas.listar_ventas(con, desde, hasta)):
        estado = f"ANULADA: {v['motivo_anulacion']}" if v["anulada"] else "Válida"
        filas.append([v["numero"], v["fecha"], v["hora"][:5], v["cliente"], ventas.FORMAS_PAGO[v["forma_pago"]],
                      v["iva"], v["total"], estado])
    validas = [f for f in filas if f[-1] == "Válida"]
    totales = ["", "", "", f"{len(validas)} ventas válidas", "", sum(f[5] for f in validas), sum(f[6] for f in validas), ""]
    return Reporte(
        "Detalle de ventas",
        [("N°", "entero", 60), ("Fecha", "fecha", 90), ("Hora", "texto", 60), ("Cliente", "texto", 240),
         ("Pago", "texto", 80), ("IVA", "dinero", 80), ("Total", "dinero", 100), ("Estado", "texto", 200)],
        filas, totales, subtitulo=_periodo(desde, hasta),
    )


def productos_vendidos(con, desde, hasta, unidad=""):
    filas = []
    for f in con.execute(
        """SELECT d.descripcion, SUM(d.cantidad),
                  SUM(CASE WHEN d.aplica_iva = 1 THEN d.total / (1 + v.iva_pct / 100.0) ELSE d.total END),
                  SUM(CASE WHEN d.insumo_id IS NOT NULL THEN d.cantidad * d.costo_unit END)
           FROM venta_detalle d JOIN ventas v ON v.id = d.venta_id
           WHERE v.anulada = 0 AND v.fecha BETWEEN ? AND ?
           GROUP BY d.producto_id ORDER BY 3 DESC""",
        (desde, hasta),
    ):
        nombre, cantidad, venta, costo = f
        margen = r2(venta - costo) if costo is not None else None
        filas.append([nombre, cantidad, r2(venta), r2(costo) if costo is not None else None, margen])
    totales = ["TOTAL", sum(f[1] for f in filas), r2(sum(f[2] for f in filas)),
               r2(sum(f[3] or 0 for f in filas)), r2(sum(f[4] or 0 for f in filas))]
    return Reporte(
        "Productos vendidos",
        [("Producto", "texto", 260), ("Cantidad", "cant", 90), ("Venta sin IVA", "dinero", 110),
         ("Costo bodega", "dinero", 110), ("Margen", "dinero", 110)],
        filas, totales, subtitulo=_periodo(desde, hasta),
        resumen=[("Nota", "El costo y margen solo se calculan para productos vinculados a un insumo de bodega "
                          "(bebidas, snacks). El costo de los platos preparados está en «Costos y margen».")],
    )


def costos_margen(con, desde, hasta, unidad=""):
    p = (desde, hasta)

    def costo(*origenes):
        marcas = ", ".join("?" * len(origenes))
        return r2(_uno(con, f"SELECT SUM(-cantidad * costo_unit) FROM movimientos "
                            f"WHERE fecha BETWEEN ? AND ? AND origen IN ({marcas})", p + origenes))

    n_rac = _uno(con, "SELECT COUNT(*) FROM raciones WHERE fecha BETWEEN ? AND ?", p)
    ing_rac = r2(_uno(con, "SELECT SUM(precio) FROM raciones WHERE fecha BETWEEN ? AND ?", p))
    n_ven = _uno(con, "SELECT COUNT(*) FROM ventas WHERE anulada = 0 AND fecha BETWEEN ? AND ?", p)
    ing_ven = r2(_uno(con, "SELECT SUM(subtotal_0 + base_iva) FROM ventas WHERE anulada = 0 AND fecha BETWEEN ? AND ?", p))
    iva_ven = r2(_uno(con, "SELECT SUM(iva) FROM ventas WHERE anulada = 0 AND fecha BETWEEN ? AND ?", p))
    platos = _uno(con, """SELECT SUM(d.cantidad) FROM venta_detalle d JOIN ventas v ON v.id = d.venta_id
                         WHERE v.anulada = 0 AND v.fecha BETWEEN ? AND ? AND d.insumo_id IS NULL""", p)
    c_cocina = costo("COCINA")
    c_ventas = costo("VENTA", "ANULACION")
    c_merma = costo("MERMA")
    c_ajuste = costo("AJUSTE")
    total_ing = r2(ing_rac + ing_ven)
    total_cos = r2(c_cocina + c_ventas + c_merma + c_ajuste)
    resultado = r2(total_ing - total_cos)
    servidos = n_rac + platos
    filas = [
        ["INGRESOS", "", None],
        ["   Raciones institucionales", n_rac, ing_rac],
        ["   Ventas de caja (sin IVA)", n_ven, ing_ven],
        ["Total ingresos", "", total_ing],
        ["COSTOS (salidas de bodega al costo)", "", None],
        ["   Insumos entregados a cocina", "", c_cocina],
        ["   Costo de productos vendidos (bebidas, snacks)", "", c_ventas],
        ["   Mermas y desperdicios", "", c_merma],
        ["   Ajustes de inventario (faltantes − sobrantes)", "", c_ajuste],
        ["Total costos", "", total_cos],
        ["RESULTADO (ingresos − costos)", "", resultado],
    ]
    return Reporte(
        "Costos y margen",
        [("Concepto", "texto", 380), ("Cantidad", "entero", 90), ("Valor", "dinero", 120)],
        filas, subtitulo=_periodo(desde, hasta),
        resumen=[
            ("Margen sobre ingresos", f"{resultado / total_ing * 100:.1f} %" if total_ing else "—"),
            ("Platos servidos (raciones + platos vendidos)", f"{fmt_cant(servidos)}"),
            ("Costo promedio de insumos de cocina por plato", fmt_dinero(c_cocina / servidos) if servidos else "—"),
            ("IVA cobrado en ventas (no es ingreso del comedor)", fmt_dinero(iva_ven)),
            ("Nota", "Las compras no son costo hasta que los insumos salen de bodega."),
        ],
    )


def consumo_insumos(con, desde, hasta, unidad=""):
    filas = [list(f) for f in con.execute(
        """SELECT i.nombre, i.unidad,
                  SUM(CASE WHEN m.origen = 'COCINA' THEN -m.cantidad ELSE 0 END),
                  SUM(CASE WHEN m.origen IN ('VENTA', 'ANULACION') THEN -m.cantidad ELSE 0 END),
                  SUM(CASE WHEN m.origen = 'MERMA' THEN -m.cantidad ELSE 0 END),
                  SUM(-m.cantidad * m.costo_unit)
           FROM movimientos m JOIN insumos i ON i.id = m.insumo_id
           WHERE m.fecha BETWEEN ? AND ? AND m.origen IN ('COCINA', 'VENTA', 'ANULACION', 'MERMA')
           GROUP BY i.id ORDER BY 6 DESC""",
        (desde, hasta),
    )]
    return Reporte(
        "Consumo de insumos",
        [("Insumo", "texto", 220), ("Unidad", "texto", 70), ("Cocina", "cant", 90), ("Ventas", "cant", 90),
         ("Merma", "cant", 90), ("Costo total", "dinero", 110)],
        filas, ["TOTAL", "", None, None, None, r2(sum(f[5] for f in filas))], subtitulo=_periodo(desde, hasta),
    )


def compras_periodo(con, desde, hasta, unidad=""):
    filas = [[c["fecha"], c["proveedor"], c["documento"], c["subtotal_0"], c["subtotal_iva"], c["iva"], c["total"]]
             for c in reversed(inventario.compras(con, desde, hasta))]
    totales = ["TOTAL", f"{len(filas)} compras", ""] + [r2(sum(f[i] for f in filas)) for i in range(3, 7)]
    return Reporte(
        "Compras de insumos",
        [("Fecha", "fecha", 90), ("Proveedor", "texto", 220), ("Documento", "texto", 130),
         ("Subtotal 0%", "dinero", 100), ("Subtotal IVA", "dinero", 100), ("IVA", "dinero", 90), ("Total", "dinero", 110)],
        filas, totales, subtitulo=_periodo(desde, hasta),
    )


def existencias(con, desde=None, hasta=None, unidad=""):
    filas = []
    bajos = 0
    for i in inventario.insumos(con):
        bajo = i["stock_minimo"] > 0 and i["stock"] <= i["stock_minimo"]
        bajos += bajo
        filas.append([i["nombre"], i["categoria"], i["unidad"], i["stock"], i["stock_minimo"], i["costo_promedio"],
                      r2(i["stock"] * i["costo_promedio"]), "BAJO MÍNIMO" if bajo else ""])
    return Reporte(
        "Existencias de bodega",
        [("Insumo", "texto", 220), ("Categoría", "texto", 120), ("Unidad", "texto", 70), ("Stock", "cant", 90),
         ("Mínimo", "cant", 80), ("Costo prom.", "dinero", 100), ("Valor", "dinero", 110), ("Estado", "texto", 110)],
        filas, ["TOTAL", "", "", None, None, None, r2(sum(f[6] for f in filas)), ""],
        subtitulo="Al momento de generar el reporte",
        resumen=[("Insumos bajo el stock mínimo", str(bajos))],
    )


def saldos_credito(con, desde=None, hasta=None, unidad=""):
    filas = [[s["cedula"], s["grado"], s["nombres"], s["unidad"], s["cargos"], s["abonos"], s["saldo"]]
             for s in ventas.saldos_credito(con)
             if (s["saldo"] or s["cargos"]) and (not unidad or s["unidad"] == unidad)]
    totales = ["", "", "TOTAL", ""] + [r2(sum(f[i] for f in filas)) for i in (4, 5, 6)]
    return Reporte(
        "Saldos de crédito del personal",
        [("Cédula", "texto", 100), ("Grado", "texto", 120), ("Apellidos y nombres", "texto", 240),
         ("Unidad", "texto", 140), ("Consumos", "dinero", 100), ("Pagos", "dinero", 100), ("Saldo", "dinero", 110)],
        filas, totales, subtitulo="Saldos acumulados a la fecha" + (f" · Unidad: {unidad}" if unidad else ""),
    )


# (nombre, función, usa_fechas, usa_unidad)
CATALOGO = [
    ("Resumen general", resumen_general, True, False),
    ("Liquidación de raciones (Armada)", liquidacion_raciones, True, True),
    ("Costos y margen", costos_margen, True, False),
    ("Ventas por día", ventas_por_dia, True, False),
    ("Detalle de ventas", detalle_ventas, True, False),
    ("Productos vendidos", productos_vendidos, True, False),
    ("Consumo de insumos", consumo_insumos, True, False),
    ("Compras de insumos", compras_periodo, True, False),
    ("Existencias de bodega", existencias, False, False),
    ("Saldos de crédito", saldos_credito, False, True),
]


# --- Reportes de detalle (se abren desde otras pantallas) ---------------------------

def estado_cuenta(con, personal_id, desde, hasta):
    persona = personal.obtener(con, personal_id)
    inicial, movs = ventas.movimientos_credito(con, personal_id, desde, hasta)
    saldo = inicial
    filas = [[desde, "Saldo anterior", None, None, inicial]]
    for m in movs:
        saldo = r2(saldo + m["cargo"] - m["abono"])
        filas.append([m["fecha"], m["concepto"], m["cargo"] or None, m["abono"] or None, saldo])
    cargos = r2(sum(m["cargo"] for m in movs))
    abonos = r2(sum(m["abono"] for m in movs))
    return Reporte(
        f"Estado de cuenta – {personal.nombre_completo(persona)}",
        [("Fecha", "fecha", 90), ("Concepto", "texto", 280), ("Consumo", "dinero", 100), ("Pago", "dinero", 100),
         ("Saldo", "dinero", 110)],
        filas, ["", "TOTALES DEL PERÍODO", cargos, abonos, saldo],
        subtitulo=f"Cédula {persona['cedula']} · {persona['unidad']} · {_periodo(desde, hasta)}",
        resumen=[("Saldo pendiente al cierre", fmt_dinero(saldo))],
    )


def kardex(con, insumo_id, desde, hasta):
    ins = inventario.obtener_insumo(con, insumo_id)
    saldo = 0.0
    inicial = 0.0
    filas = []
    for m in inventario.movimientos(con, insumo_id):
        saldo = round(saldo + m["cantidad"], 4)
        if m["fecha"] < desde:
            inicial = saldo
            continue
        if m["fecha"] > hasta:
            break
        detalle = " · ".join(x for x in (m["referencia"], m["tiempo"], m["nota"]) if x)
        filas.append([m["fecha"], m["origen"].capitalize(), detalle,
                      m["cantidad"] if m["cantidad"] > 0 else None, -m["cantidad"] if m["cantidad"] < 0 else None,
                      saldo, m["costo_unit"]])
    filas.insert(0, [desde, "Saldo inicial", "", None, None, inicial, None])
    return Reporte(
        f"Kardex – {ins['nombre']} ({ins['unidad']})",
        [("Fecha", "fecha", 90), ("Movimiento", "texto", 100), ("Detalle", "texto", 260), ("Entrada", "cant", 80),
         ("Salida", "cant", 80), ("Saldo", "cant", 80), ("Costo unit.", "dinero", 100)],
        filas, subtitulo=_periodo(desde, hasta),
        resumen=[("Stock actual", f"{fmt_cant(ins['stock'])} {ins['unidad']}"),
                 ("Costo promedio actual", fmt_dinero(ins["costo_promedio"]))],
    )


# --- Exportación ---------------------------------------------------------------------

def _separadores():
    """Separador decimal y de columnas según la configuración regional de Windows (para Excel)."""
    try:
        locale.setlocale(locale.LC_NUMERIC, "")
        decimal = locale.localeconv().get("decimal_point") or "."
    except locale.Error:
        decimal = "."
    return decimal, (";" if decimal == "," else ",")


def exportar_csv(reporte, ruta):
    decimal, separador = _separadores()

    def celda(valor, tipo):
        if valor is None or valor == "":
            return ""
        if tipo in ("dinero", "cant", "pct") and isinstance(valor, (int, float)):
            texto = f"{valor:.2f}" if tipo == "dinero" else f"{valor:.3f}".rstrip("0").rstrip(".")
            return texto.replace(".", decimal)
        if tipo == "fecha":
            return fecha_ver(valor)
        return str(valor)

    tipos = [c[1] for c in reporte.columnas]
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        escritor = csv.writer(f, delimiter=separador)
        escritor.writerow([reporte.titulo])
        if reporte.subtitulo:
            escritor.writerow([reporte.subtitulo])
        escritor.writerow([])
        escritor.writerow([c[0] for c in reporte.columnas])
        for fila in reporte.filas:
            escritor.writerow([celda(v, t) for v, t in zip(fila, tipos)])
        if reporte.totales:
            escritor.writerow([celda(v, t) for v, t in zip(reporte.totales, tipos)])
        if reporte.resumen:
            escritor.writerow([])
            for etiqueta, texto in reporte.resumen:
                escritor.writerow([etiqueta, texto])
