"""Raciones institucionales: lo que el comedor factura a la Armada por persona y tiempo de comida."""
import sqlite3

from . import personal
from .util import ErrorNegocio, fecha_ver, r2


def tiempos(con):
    return con.execute("SELECT * FROM tiempos_comida ORDER BY orden").fetchall()


def obtener_tiempo(con, tiempo_id):
    fila = con.execute("SELECT * FROM tiempos_comida WHERE id = ?", (tiempo_id,)).fetchone()
    if not fila:
        raise ErrorNegocio("Seleccione el tiempo de comida.")
    return fila


def guardar_precios(con, precios):
    """precios: {tiempo_id: precio por ración}."""
    for precio in precios.values():
        if precio < 0:
            raise ErrorNegocio("El precio de la ración no puede ser negativo.")
    with con:
        con.executemany(
            "UPDATE tiempos_comida SET precio_racion = ? WHERE id = ?",
            [(r2(p), tid) for tid, p in precios.items()],
        )


def _validar_persona(persona):
    if not persona["activo"]:
        raise ErrorNegocio(f"{personal.nombre_completo(persona)} está registrado como INACTIVO.")
    if not persona["racion_institucional"]:
        raise ErrorNegocio(f"{personal.nombre_completo(persona)} no tiene ración pagada por la institución.")


def registrar(con, fecha, tiempo_id, cedula):
    """Registra la ración de una persona identificada por su cédula y la devuelve."""
    cedula = str(cedula).strip()
    persona = personal.por_cedula(con, cedula)
    if not persona:
        raise ErrorNegocio(f"No existe personal con cédula {cedula}.")
    _validar_persona(persona)
    tiempo = obtener_tiempo(con, tiempo_id)
    try:
        with con:
            con.execute(
                "INSERT INTO raciones(fecha, tiempo_id, personal_id, precio) VALUES (?, ?, ?, ?)",
                (fecha, tiempo_id, persona["id"], tiempo["precio_racion"]),
            )
    except sqlite3.IntegrityError:
        raise ErrorNegocio(
            f"{personal.nombre_completo(persona)} ya tiene registrado el {tiempo['nombre'].lower()} "
            f"del {fecha_ver(fecha)}."
        ) from None
    return persona


def registrar_varios(con, fecha, tiempo_id, personal_ids):
    """Registra raciones a varias personas. Devuelve (registradas, ya_existentes, rechazadas)."""
    tiempo = obtener_tiempo(con, tiempo_id)
    registradas = existentes = 0
    rechazadas = []
    with con:
        for pid in personal_ids:
            persona = personal.obtener(con, pid)
            try:
                _validar_persona(persona)
            except ErrorNegocio as e:
                rechazadas.append(str(e))
                continue
            cur = con.execute(
                "INSERT OR IGNORE INTO raciones(fecha, tiempo_id, personal_id, precio) VALUES (?, ?, ?, ?)",
                (fecha, tiempo_id, pid, tiempo["precio_racion"]),
            )
            if cur.rowcount:
                registradas += 1
            else:
                existentes += 1
    return registradas, existentes, rechazadas


def eliminar(con, racion_ids):
    with con:
        con.executemany("DELETE FROM raciones WHERE id = ?", [(i,) for i in racion_ids])


def listar(con, fecha, tiempo_id):
    return con.execute(
        """SELECT r.id, r.registrado, r.precio, p.cedula, p.grado, p.nombres, p.unidad
           FROM raciones r JOIN personal p ON p.id = r.personal_id
           WHERE r.fecha = ? AND r.tiempo_id = ?
           ORDER BY r.registrado DESC, r.id DESC""",
        (fecha, tiempo_id),
    ).fetchall()


def resumen_dia(con, fecha):
    return con.execute(
        """SELECT t.id, t.nombre, COUNT(r.id) AS cantidad, COALESCE(SUM(r.precio), 0) AS total
           FROM tiempos_comida t LEFT JOIN raciones r ON r.tiempo_id = t.id AND r.fecha = ?
           GROUP BY t.id ORDER BY t.orden""",
        (fecha,),
    ).fetchall()
