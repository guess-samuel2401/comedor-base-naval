"""Conexión, esquema y configuración de la base de datos SQLite."""
import os
import sqlite3
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RUTA_DB = Path(os.environ.get("COMEDOR_DB") or RAIZ / "datos" / "comedor.db")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS config (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS personal (
    id INTEGER PRIMARY KEY,
    cedula TEXT NOT NULL UNIQUE,
    grado TEXT NOT NULL DEFAULT '',
    nombres TEXT NOT NULL,
    unidad TEXT NOT NULL DEFAULT '',
    racion_institucional INTEGER NOT NULL DEFAULT 1,  -- la Armada paga su ración
    credito INTEGER NOT NULL DEFAULT 0,               -- autorizado a consumir a crédito
    limite_credito REAL NOT NULL DEFAULT 0,           -- 0 = sin límite
    activo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS tiempos_comida (
    id INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE,
    orden INTEGER NOT NULL,
    precio_racion REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS raciones (
    id INTEGER PRIMARY KEY,
    fecha TEXT NOT NULL,
    tiempo_id INTEGER NOT NULL REFERENCES tiempos_comida(id),
    personal_id INTEGER NOT NULL REFERENCES personal(id),
    precio REAL NOT NULL,
    registrado TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE (fecha, tiempo_id, personal_id)
);
CREATE INDEX IF NOT EXISTS ix_raciones_fecha ON raciones(fecha);

CREATE TABLE IF NOT EXISTS insumos (
    id INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE,
    categoria TEXT NOT NULL DEFAULT '',
    unidad TEXT NOT NULL DEFAULT 'kg',
    stock REAL NOT NULL DEFAULT 0,
    stock_minimo REAL NOT NULL DEFAULT 0,
    costo_promedio REAL NOT NULL DEFAULT 0,
    activo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS productos (
    id INTEGER PRIMARY KEY,
    codigo TEXT UNIQUE,
    nombre TEXT NOT NULL,
    categoria TEXT NOT NULL DEFAULT '',
    precio REAL NOT NULL,                       -- precio final de venta (PVP)
    aplica_iva INTEGER NOT NULL DEFAULT 0,
    insumo_id INTEGER REFERENCES insumos(id),   -- se descuenta de bodega al vender
    activo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS ventas (
    id INTEGER PRIMARY KEY,
    numero INTEGER NOT NULL UNIQUE,
    fecha TEXT NOT NULL,
    hora TEXT NOT NULL,
    personal_id INTEGER REFERENCES personal(id),
    cliente TEXT NOT NULL,
    forma_pago TEXT NOT NULL CHECK (forma_pago IN ('CONTADO', 'CREDITO')),
    subtotal_0 REAL NOT NULL,
    base_iva REAL NOT NULL,
    iva REAL NOT NULL,
    total REAL NOT NULL,
    iva_pct REAL NOT NULL,
    anulada INTEGER NOT NULL DEFAULT 0,
    motivo_anulacion TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_ventas_fecha ON ventas(fecha);

CREATE TABLE IF NOT EXISTS venta_detalle (
    id INTEGER PRIMARY KEY,
    venta_id INTEGER NOT NULL REFERENCES ventas(id),
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    descripcion TEXT NOT NULL,
    cantidad REAL NOT NULL,
    precio REAL NOT NULL,
    aplica_iva INTEGER NOT NULL,
    total REAL NOT NULL,
    insumo_id INTEGER REFERENCES insumos(id),
    costo_unit REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cobros (
    id INTEGER PRIMARY KEY,
    fecha TEXT NOT NULL,
    personal_id INTEGER NOT NULL REFERENCES personal(id),
    monto REAL NOT NULL CHECK (monto > 0),
    detalle TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS proveedores (
    id INTEGER PRIMARY KEY,
    ruc TEXT NOT NULL DEFAULT '',
    nombre TEXT NOT NULL UNIQUE,
    telefono TEXT NOT NULL DEFAULT '',
    direccion TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS compras (
    id INTEGER PRIMARY KEY,
    fecha TEXT NOT NULL,
    proveedor_id INTEGER REFERENCES proveedores(id),
    documento TEXT NOT NULL DEFAULT '',
    subtotal_0 REAL NOT NULL DEFAULT 0,
    subtotal_iva REAL NOT NULL DEFAULT 0,
    iva REAL NOT NULL DEFAULT 0,
    total REAL NOT NULL DEFAULT 0,
    iva_pct REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS compra_detalle (
    id INTEGER PRIMARY KEY,
    compra_id INTEGER NOT NULL REFERENCES compras(id),
    insumo_id INTEGER NOT NULL REFERENCES insumos(id),
    cantidad REAL NOT NULL,
    costo_unit REAL NOT NULL,      -- sin IVA, tal como viene en la factura
    aplica_iva INTEGER NOT NULL,
    total REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS movimientos (
    id INTEGER PRIMARY KEY,
    fecha TEXT NOT NULL,
    insumo_id INTEGER NOT NULL REFERENCES insumos(id),
    tipo TEXT NOT NULL CHECK (tipo IN ('ENTRADA', 'SALIDA', 'AJUSTE')),
    origen TEXT NOT NULL,          -- COMPRA, VENTA, ANULACION, COCINA, MERMA, AJUSTE, INICIAL
    cantidad REAL NOT NULL,        -- positiva entra, negativa sale
    costo_unit REAL NOT NULL,
    tiempo_id INTEGER REFERENCES tiempos_comida(id),
    referencia TEXT NOT NULL DEFAULT '',
    nota TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_movimientos_fecha ON movimientos(fecha);
"""

CONFIG_INICIAL = {
    "nombre_comedor": "Comedor de Tripulación",
    "entidad": "Base Naval",
    "direccion": "",
    "iva_pct": "15",
}

TIEMPOS_INICIALES = [("Desayuno", 1, 0.0), ("Almuerzo", 2, 0.0), ("Merienda", 3, 0.0)]


def conectar(ruta=None):
    """Abre la base de datos, creando el esquema y los datos iniciales si hace falta."""
    ruta = str(ruta or RUTA_DB)
    if ruta != ":memory:":
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(ruta)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(ESQUEMA)
    with con:
        con.executemany("INSERT OR IGNORE INTO config(clave, valor) VALUES (?, ?)", CONFIG_INICIAL.items())
        if not con.execute("SELECT 1 FROM tiempos_comida").fetchone():
            con.executemany(
                "INSERT INTO tiempos_comida(nombre, orden, precio_racion) VALUES (?, ?, ?)", TIEMPOS_INICIALES
            )
    return con


def config(con, clave, defecto=""):
    fila = con.execute("SELECT valor FROM config WHERE clave = ?", (clave,)).fetchone()
    return fila["valor"] if fila else defecto


def guardar_config(con, valores):
    with con:
        con.executemany(
            "INSERT INTO config(clave, valor) VALUES (?, ?) ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
            [(k, str(v)) for k, v in valores.items()],
        )


def iva_pct(con):
    return float(config(con, "iva_pct", "15") or 0)


def encabezado(con):
    """Datos del comedor para comprobantes y reportes."""
    return {clave: config(con, clave) for clave in ("nombre_comedor", "entidad", "direccion")}


def carpeta_impresiones():
    carpeta = RUTA_DB.parent / "impresiones"
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def respaldar(con, destino):
    """Copia completa y consistente de la base de datos al archivo indicado."""
    copia = sqlite3.connect(destino)
    try:
        con.backup(copia)
    finally:
        copia.close()
