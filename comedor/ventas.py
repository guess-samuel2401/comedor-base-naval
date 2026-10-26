"""Caja: productos, ventas de contado y a crédito, y cobros de crédito.

El precio de cada producto es el precio final (PVP). Si el producto grava IVA, el
comprobante desglosa la base imponible y el IVA incluidos en ese precio."""
import sqlite3

from . import inventario, personal
from .db import iva_pct
from .util import ErrorNegocio, fmt_dinero, hora_actual, hoy, r2

FORMAS_PAGO = {"CONTADO": "Contado", "CREDITO": "Crédito"}
CATEGORIAS = ["Menú", "Bebidas", "Snacks", "Otros"]


# --- Productos ---------------------------------------------------------------

def productos(con, texto="", solo_activos=True):
    sql = """SELECT p.*, i.nombre AS insumo, i.stock AS stock, i.unidad AS unidad
             FROM productos p LEFT JOIN insumos i ON i.id = p.insumo_id
             WHERE (p.nombre LIKE ? OR IFNULL(p.codigo, '') LIKE ? OR p.categoria LIKE ?)"""
    if solo_activos:
        sql += " AND p.activo = 1"
    return con.execute(sql + " ORDER BY p.categoria, p.nombre", (f"%{texto}%",) * 3).fetchall()


def obtener_producto(con, producto_id):
    fila = con.execute("SELECT * FROM productos WHERE id = ?", (producto_id,)).fetchone()
    if not fila:
        raise ErrorNegocio("El producto no existe.")
    return fila


def categorias(con):
    usadas = [f[0] for f in con.execute("SELECT DISTINCT categoria FROM productos WHERE categoria <> '' ORDER BY 1")]
    return CATEGORIAS + [c for c in usadas if c not in CATEGORIAS]


def guardar_producto(con, datos, producto_id=None):
    nombre = str(datos.get("nombre", "")).strip()
    if not nombre:
        raise ErrorNegocio("El nombre del producto es obligatorio.")
    precio = r2(datos.get("precio") or 0)
    if precio <= 0:
        raise ErrorNegocio("El precio de venta debe ser mayor que cero.")
    codigo = str(datos.get("codigo") or "").strip() or None
    valores = (
        codigo,
        nombre,
        str(datos.get("categoria", "")).strip(),
        precio,
        int(bool(datos.get("aplica_iva"))),
        datos.get("insumo_id") or None,
        int(bool(datos.get("activo", True))),
    )
    try:
        with con:
            if producto_id:
                con.execute(
                    """UPDATE productos SET codigo = ?, nombre = ?, categoria = ?, precio = ?, aplica_iva = ?,
                       insumo_id = ?, activo = ? WHERE id = ?""",
                    valores + (producto_id,),
                )
                return producto_id
            return con.execute(
                """INSERT INTO productos(codigo, nombre, categoria, precio, aplica_iva, insumo_id, activo)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                valores,
            ).lastrowid
    except sqlite3.IntegrityError:
        raise ErrorNegocio(f"Ya existe un producto con el código {codigo}.") from None


# --- Ventas ------------------------------------------------------------------

def calcular_totales(lineas, pct):
    """lineas: dicts con total y aplica_iva. Desglosa el IVA incluido en los precios."""
    sub0 = r2(sum(l["total"] for l in lineas if not l["aplica_iva"]))
    con_iva = r2(sum(l["total"] for l in lineas if l["aplica_iva"]))
    base = r2(con_iva / (1 + pct / 100))
    return {"subtotal_0": sub0, "base_iva": base, "iva": r2(con_iva - base), "total": r2(sub0 + con_iva)}


def _preparar_lineas(con, lineas):
    items = []
    for l in lineas:
        prod = obtener_producto(con, l["producto_id"])
        cantidad = round(float(l["cantidad"]), 3)
        if cantidad <= 0:
            raise ErrorNegocio(f"Cantidad inválida para {prod['nombre']}.")
        precio = r2(l.get("precio", prod["precio"]))
        items.append({
            "producto_id": prod["id"], "descripcion": prod["nombre"], "cantidad": cantidad, "precio": precio,
            "aplica_iva": bool(prod["aplica_iva"]), "total": r2(cantidad * precio), "insumo_id": prod["insumo_id"],
        })
    return items


def registrar_venta(con, lineas, forma_pago="CONTADO", personal_id=None, cliente="", fecha=None):
    """Registra una venta, descuenta de bodega los productos vinculados y devuelve su id."""
    if not lineas:
        raise ErrorNegocio("La venta no tiene productos.")
    forma_pago = str(forma_pago).upper()
    if forma_pago not in FORMAS_PAGO:
        raise ErrorNegocio(f"Forma de pago inválida: {forma_pago}.")
    fecha = fecha or hoy()
    pct = iva_pct(con)
    items = _preparar_lineas(con, lineas)
    tot = calcular_totales(items, pct)
    persona = personal.obtener(con, personal_id) if personal_id else None

    if forma_pago == "CREDITO":
        if not persona:
            raise ErrorNegocio("Para vender a crédito ingrese la cédula de la persona.")
        if not persona["credito"] or not persona["activo"]:
            raise ErrorNegocio(f"{personal.nombre_completo(persona)} no está autorizado para consumir a crédito.")
        limite = persona["limite_credito"]
        if limite > 0:
            saldo = saldo_credito(con, persona["id"])
            if saldo + tot["total"] > limite + 0.001:
                raise ErrorNegocio(
                    f"La venta supera el límite de crédito de {personal.nombre_completo(persona)}.\n"
                    f"Límite: {fmt_dinero(limite)} · Saldo actual: {fmt_dinero(saldo)} · "
                    f"Disponible: {fmt_dinero(max(limite - saldo, 0))}"
                )

    if persona:
        cliente = personal.nombre_completo(persona)
    cliente = str(cliente or "").strip() or "Consumidor final"

    with con:
        numero = con.execute("SELECT COALESCE(MAX(numero), 0) + 1 FROM ventas").fetchone()[0]
        venta_id = con.execute(
            """INSERT INTO ventas(numero, fecha, hora, personal_id, cliente, forma_pago,
                                  subtotal_0, base_iva, iva, total, iva_pct)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (numero, fecha, hora_actual(), persona["id"] if persona else None, cliente, forma_pago,
             tot["subtotal_0"], tot["base_iva"], tot["iva"], tot["total"], pct),
        ).lastrowid
        for it in items:
            costo = 0.0
            if it["insumo_id"]:
                costo = inventario.obtener_insumo(con, it["insumo_id"])["costo_promedio"]
                inventario._mover(con, it["insumo_id"], -it["cantidad"], costo, "SALIDA", "VENTA", fecha,
                                  referencia=f"Venta N° {numero}")
            con.execute(
                """INSERT INTO venta_detalle(venta_id, producto_id, descripcion, cantidad, precio, aplica_iva,
                                             total, insumo_id, costo_unit)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (venta_id, it["producto_id"], it["descripcion"], it["cantidad"], it["precio"],
                 int(it["aplica_iva"]), it["total"], it["insumo_id"], costo),
            )
    return venta_id


def obtener(con, venta_id):
    venta = con.execute("SELECT * FROM ventas WHERE id = ?", (venta_id,)).fetchone()
    if not venta:
        raise ErrorNegocio("La venta no existe.")
    detalle = con.execute("SELECT * FROM venta_detalle WHERE venta_id = ? ORDER BY id", (venta_id,)).fetchall()
    return venta, detalle


def anular_venta(con, venta_id, motivo):
    """Anula una venta y devuelve a bodega los productos que se habían descontado."""
    motivo = str(motivo or "").strip()
    if not motivo:
        raise ErrorNegocio("Indique el motivo de la anulación.")
    venta, detalle = obtener(con, venta_id)
    if venta["anulada"]:
        raise ErrorNegocio(f"La venta N° {venta['numero']} ya está anulada.")
    with con:
        con.execute("UPDATE ventas SET anulada = 1, motivo_anulacion = ? WHERE id = ?", (motivo, venta_id))
        for d in detalle:
            if d["insumo_id"]:
                # Misma fecha que la venta, para que los reportes del período cuadren.
                inventario._mover(con, d["insumo_id"], d["cantidad"], d["costo_unit"], "ENTRADA", "ANULACION",
                                  venta["fecha"], referencia=f"Anulación venta N° {venta['numero']}", nota=motivo)


def listar_ventas(con, desde, hasta):
    return con.execute(
        "SELECT * FROM ventas WHERE fecha BETWEEN ? AND ? ORDER BY numero DESC", (desde, hasta)
    ).fetchall()


# --- Crédito -------------------------------------------------------------------

def saldo_credito(con, personal_id, antes_de=None):
    filtro_v = " AND fecha < ?" if antes_de else ""
    parametros = (personal_id, antes_de) if antes_de else (personal_id,)
    cargos = con.execute(
        f"""SELECT COALESCE(SUM(total), 0) FROM ventas
            WHERE personal_id = ? AND forma_pago = 'CREDITO' AND anulada = 0{filtro_v}""",
        parametros,
    ).fetchone()[0]
    abonos = con.execute(
        f"SELECT COALESCE(SUM(monto), 0) FROM cobros WHERE personal_id = ?{filtro_v}", parametros
    ).fetchone()[0]
    return r2(cargos - abonos)


def registrar_cobro(con, personal_id, monto, detalle="", fecha=None):
    monto = r2(monto)
    if monto <= 0:
        raise ErrorNegocio("El monto del cobro debe ser mayor que cero.")
    persona = personal.obtener(con, personal_id)
    saldo = saldo_credito(con, personal_id)
    if monto > saldo + 0.001:
        raise ErrorNegocio(
            f"El cobro ({fmt_dinero(monto)}) supera el saldo pendiente de "
            f"{personal.nombre_completo(persona)} ({fmt_dinero(saldo)})."
        )
    with con:
        return con.execute(
            "INSERT INTO cobros(fecha, personal_id, monto, detalle) VALUES (?, ?, ?, ?)",
            (fecha or hoy(), personal_id, monto, str(detalle or "").strip()),
        ).lastrowid


def movimientos_credito(con, personal_id, desde, hasta):
    """Devuelve (saldo_inicial, filas) con fecha, concepto, cargo y abono del período."""
    inicial = saldo_credito(con, personal_id, antes_de=desde)
    filas = con.execute(
        """SELECT fecha, 'Consumo N° ' || numero AS concepto, total AS cargo, 0 AS abono, 0 AS orden, id
           FROM ventas
           WHERE personal_id = ? AND forma_pago = 'CREDITO' AND anulada = 0 AND fecha BETWEEN ? AND ?
           UNION ALL
           SELECT fecha, 'Cobro' || CASE WHEN detalle <> '' THEN ' – ' || detalle ELSE '' END, 0, monto, 1, id
           FROM cobros WHERE personal_id = ? AND fecha BETWEEN ? AND ?
           ORDER BY fecha, orden, id""",
        (personal_id, desde, hasta, personal_id, desde, hasta),
    ).fetchall()
    return inicial, filas


def saldos_credito(con):
    filas = con.execute(
        """SELECT p.id, p.cedula, p.grado, p.nombres, p.unidad, p.credito, p.limite_credito,
                  COALESCE((SELECT SUM(total) FROM ventas v WHERE v.personal_id = p.id
                            AND v.forma_pago = 'CREDITO' AND v.anulada = 0), 0) AS cargos,
                  COALESCE((SELECT SUM(monto) FROM cobros c WHERE c.personal_id = p.id), 0) AS abonos
           FROM personal p
           WHERE p.credito = 1 OR EXISTS (SELECT 1 FROM ventas v WHERE v.personal_id = p.id AND v.forma_pago = 'CREDITO')
           ORDER BY p.nombres"""
    ).fetchall()
    return [dict(f, saldo=r2(f["cargos"] - f["abonos"])) for f in filas]
