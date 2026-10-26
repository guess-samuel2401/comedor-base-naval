"""Bodega: insumos, proveedores, compras, salidas y ajustes de inventario.

El costo de cada insumo se lleva por promedio ponderado. Como el comedor no recupera
el IVA de sus compras, el IVA pagado forma parte del costo del insumo."""
import sqlite3

from .db import iva_pct
from .util import ErrorNegocio, fmt_cant, hoy, r2

ORIGENES_SALIDA = {"COCINA": "Consumo de cocina", "MERMA": "Merma / desperdicio"}
UNIDADES = ["kg", "lb", "g", "litro", "ml", "galón", "unidad", "paquete", "caja", "funda", "docena", "quintal"]
CATEGORIAS = ["Abarrotes", "Granos", "Carnes", "Pescados y mariscos", "Lácteos", "Frutas", "Verduras",
              "Bebidas", "Snacks", "Condimentos", "Limpieza", "Descartables"]


# --- Insumos ---------------------------------------------------------------

def insumos(con, texto="", solo_activos=True):
    sql = "SELECT * FROM insumos WHERE (nombre LIKE ? OR categoria LIKE ?)"
    if solo_activos:
        sql += " AND activo = 1"
    return con.execute(sql + " ORDER BY nombre", (f"%{texto}%", f"%{texto}%")).fetchall()


def obtener_insumo(con, insumo_id):
    fila = con.execute("SELECT * FROM insumos WHERE id = ?", (insumo_id,)).fetchone()
    if not fila:
        raise ErrorNegocio("El insumo no existe.")
    return fila


def categorias(con):
    usadas = [f[0] for f in con.execute("SELECT DISTINCT categoria FROM insumos WHERE categoria <> '' ORDER BY 1")]
    return CATEGORIAS + [c for c in usadas if c not in CATEGORIAS]


def guardar_insumo(con, datos, insumo_id=None):
    nombre = str(datos.get("nombre", "")).strip()
    if not nombre:
        raise ErrorNegocio("El nombre del insumo es obligatorio.")
    minimo = float(datos.get("stock_minimo") or 0)
    if minimo < 0:
        raise ErrorNegocio("El stock mínimo no puede ser negativo.")
    valores = (
        nombre,
        str(datos.get("categoria", "")).strip(),
        str(datos.get("unidad", "")).strip() or "unidad",
        minimo,
        int(bool(datos.get("activo", True))),
    )
    try:
        with con:
            if insumo_id:
                con.execute(
                    "UPDATE insumos SET nombre = ?, categoria = ?, unidad = ?, stock_minimo = ?, activo = ? WHERE id = ?",
                    valores + (insumo_id,),
                )
                return insumo_id
            return con.execute(
                "INSERT INTO insumos(nombre, categoria, unidad, stock_minimo, activo) VALUES (?, ?, ?, ?, ?)", valores
            ).lastrowid
    except sqlite3.IntegrityError:
        raise ErrorNegocio(f"Ya existe un insumo llamado «{nombre}».") from None


def _mover(con, insumo_id, cantidad, costo_unit, tipo, origen, fecha, referencia="", nota="", tiempo_id=None):
    """Registra un movimiento y actualiza stock y costo promedio. No confirma la transacción."""
    ins = obtener_insumo(con, insumo_id)
    stock = round(ins["stock"] + cantidad, 4)
    if stock < 0:
        raise ErrorNegocio(
            f"Stock insuficiente de {ins['nombre']}: hay {fmt_cant(ins['stock'])} {ins['unidad']} "
            f"y se requieren {fmt_cant(-cantidad)}. Registre la compra o ajuste el inventario."
        )
    costo_prom = ins["costo_promedio"]
    if cantidad > 0:
        previo = max(ins["stock"], 0)
        costo_prom = (previo * costo_prom + cantidad * costo_unit) / (previo + cantidad)
    con.execute("UPDATE insumos SET stock = ?, costo_promedio = ? WHERE id = ?", (stock, round(costo_prom, 6), insumo_id))
    con.execute(
        """INSERT INTO movimientos(fecha, insumo_id, tipo, origen, cantidad, costo_unit, tiempo_id, referencia, nota)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (fecha, insumo_id, tipo, origen, cantidad, round(costo_unit, 6), tiempo_id, referencia, nota),
    )


# --- Proveedores ------------------------------------------------------------

def proveedores(con, texto=""):
    return con.execute(
        "SELECT * FROM proveedores WHERE nombre LIKE ? OR ruc LIKE ? ORDER BY nombre", (f"%{texto}%", f"%{texto}%")
    ).fetchall()


def guardar_proveedor(con, datos, proveedor_id=None):
    nombre = str(datos.get("nombre", "")).strip()
    if not nombre:
        raise ErrorNegocio("El nombre del proveedor es obligatorio.")
    valores = tuple(str(datos.get(c, "")).strip() for c in ("ruc", "telefono", "direccion"))
    try:
        with con:
            if proveedor_id:
                con.execute(
                    "UPDATE proveedores SET nombre = ?, ruc = ?, telefono = ?, direccion = ? WHERE id = ?",
                    (nombre,) + valores + (proveedor_id,),
                )
                return proveedor_id
            return con.execute(
                "INSERT INTO proveedores(nombre, ruc, telefono, direccion) VALUES (?, ?, ?, ?)", (nombre,) + valores
            ).lastrowid
    except sqlite3.IntegrityError:
        raise ErrorNegocio(f"Ya existe un proveedor llamado «{nombre}».") from None


# --- Compras ----------------------------------------------------------------

def totales_compra(lineas, pct):
    """lineas: dicts con cantidad, costo_unit (sin IVA) y aplica_iva."""
    sub0 = r2(sum(r2(l["cantidad"] * l["costo_unit"]) for l in lineas if not l["aplica_iva"]))
    subiva = r2(sum(r2(l["cantidad"] * l["costo_unit"]) for l in lineas if l["aplica_iva"]))
    iva = r2(subiva * pct / 100)
    return {"subtotal_0": sub0, "subtotal_iva": subiva, "iva": iva, "total": r2(sub0 + subiva + iva)}


def registrar_compra(con, proveedor_id, documento, lineas, fecha=None):
    """Registra una factura de compra e ingresa los insumos a bodega. Devuelve el id de la compra."""
    if not lineas:
        raise ErrorNegocio("Agregue al menos un insumo a la compra.")
    fecha = fecha or hoy()
    pct = iva_pct(con)
    items = []
    for l in lineas:
        cantidad = round(float(l["cantidad"]), 3)
        costo = float(l["costo_unit"])
        if cantidad <= 0:
            raise ErrorNegocio("La cantidad comprada debe ser mayor que cero.")
        if costo < 0:
            raise ErrorNegocio("El costo unitario no puede ser negativo.")
        items.append({"insumo_id": l["insumo_id"], "cantidad": cantidad, "costo_unit": costo,
                      "aplica_iva": bool(l.get("aplica_iva"))})
    tot = totales_compra(items, pct)
    documento = str(documento or "").strip()
    with con:
        compra_id = con.execute(
            """INSERT INTO compras(fecha, proveedor_id, documento, subtotal_0, subtotal_iva, iva, total, iva_pct)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (fecha, proveedor_id, documento, tot["subtotal_0"], tot["subtotal_iva"], tot["iva"], tot["total"], pct),
        ).lastrowid
        referencia = f"Compra {documento}".strip() if documento else f"Compra #{compra_id}"
        for it in items:
            con.execute(
                """INSERT INTO compra_detalle(compra_id, insumo_id, cantidad, costo_unit, aplica_iva, total)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (compra_id, it["insumo_id"], it["cantidad"], it["costo_unit"], int(it["aplica_iva"]),
                 r2(it["cantidad"] * it["costo_unit"])),
            )
            costo_bodega = it["costo_unit"] * (1 + pct / 100) if it["aplica_iva"] else it["costo_unit"]
            _mover(con, it["insumo_id"], it["cantidad"], costo_bodega, "ENTRADA", "COMPRA", fecha, referencia)
    return compra_id


def compras(con, desde, hasta):
    return con.execute(
        """SELECT c.*, COALESCE(p.nombre, '(sin proveedor)') AS proveedor
           FROM compras c LEFT JOIN proveedores p ON p.id = c.proveedor_id
           WHERE c.fecha BETWEEN ? AND ? ORDER BY c.fecha DESC, c.id DESC""",
        (desde, hasta),
    ).fetchall()


def detalle_compra(con, compra_id):
    return con.execute(
        """SELECT d.*, i.nombre AS insumo, i.unidad FROM compra_detalle d JOIN insumos i ON i.id = d.insumo_id
           WHERE d.compra_id = ? ORDER BY d.id""",
        (compra_id,),
    ).fetchall()


# --- Salidas y ajustes --------------------------------------------------------

def registrar_salidas(con, fecha, lineas):
    """Salidas de bodega a cocina o por merma. lineas: insumo_id, cantidad, origen, tiempo_id, nota."""
    if not lineas:
        raise ErrorNegocio("Agregue al menos un insumo.")
    with con:
        for l in lineas:
            origen = l.get("origen", "COCINA")
            if origen not in ORIGENES_SALIDA:
                raise ErrorNegocio(f"Motivo de salida inválido: {origen}.")
            cantidad = round(float(l["cantidad"]), 3)
            if cantidad <= 0:
                raise ErrorNegocio("La cantidad de salida debe ser mayor que cero.")
            ins = obtener_insumo(con, l["insumo_id"])
            _mover(con, ins["id"], -cantidad, ins["costo_promedio"], "SALIDA", origen, fecha,
                   nota=l.get("nota", ""), tiempo_id=l.get("tiempo_id"))


def tiene_movimientos(con, insumo_id):
    return con.execute("SELECT 1 FROM movimientos WHERE insumo_id = ? LIMIT 1", (insumo_id,)).fetchone() is not None


def ajustar_stock(con, insumo_id, stock_real, nota="", fecha=None, costo_unit=None, inicial=None):
    """Iguala el stock al conteo físico. Si aumenta, el sobrante entra al costo indicado.

    Con `inicial` (por defecto: si el insumo aún no tiene movimientos) se registra como carga de
    inventario inicial, que no cuenta como sobrante en los reportes de costos."""
    ins = obtener_insumo(con, insumo_id)
    stock_real = round(float(stock_real), 3)
    if stock_real < 0:
        raise ErrorNegocio("El stock real no puede ser negativo.")
    diferencia = round(stock_real - ins["stock"], 4)
    if abs(diferencia) < 0.0005:
        raise ErrorNegocio("El stock indicado es igual al actual; no hay nada que ajustar.")
    if inicial is None:
        inicial = not tiene_movimientos(con, insumo_id)
    if inicial and diferencia < 0:
        raise ErrorNegocio("La carga de inventario inicial solo puede aumentar el stock.")
    costo = float(costo_unit) if diferencia > 0 and costo_unit else ins["costo_promedio"]
    if inicial and costo <= 0:
        raise ErrorNegocio(f"Indique el costo unitario de {ins['nombre']} para cargar el inventario inicial.")
    origen = "INICIAL" if inicial else "AJUSTE"
    with con:
        _mover(con, insumo_id, diferencia, costo, "AJUSTE", origen, fecha or hoy(),
               nota=nota or ("Inventario inicial" if inicial else "Ajuste por conteo físico"))


def salidas_del_dia(con, fecha):
    return con.execute(
        """SELECT m.*, i.nombre AS insumo, i.unidad, COALESCE(t.nombre, '') AS tiempo
           FROM movimientos m JOIN insumos i ON i.id = m.insumo_id
           LEFT JOIN tiempos_comida t ON t.id = m.tiempo_id
           WHERE m.fecha = ? AND m.origen IN ('COCINA', 'MERMA') ORDER BY m.id DESC""",
        (fecha,),
    ).fetchall()


def movimientos(con, insumo_id):
    return con.execute(
        """SELECT m.*, COALESCE(t.nombre, '') AS tiempo FROM movimientos m
           LEFT JOIN tiempos_comida t ON t.id = m.tiempo_id
           WHERE m.insumo_id = ? ORDER BY m.fecha, m.id""",
        (insumo_id,),
    ).fetchall()
