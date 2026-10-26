"""Registro del personal (marinos, empleados) que consume en el comedor."""
import csv
import io
import unicodedata

from .util import ErrorNegocio, r2

GRADOS = [
    "Marinero", "Cabo Segundo", "Cabo Primero", "Sargento Segundo", "Sargento Primero",
    "Suboficial Segundo", "Suboficial Primero", "Suboficial Mayor", "Guardiamarina",
    "Alférez de Fragata", "Teniente de Fragata", "Teniente de Navío", "Capitán de Corbeta",
    "Capitán de Fragata", "Capitán de Navío", "Contralmirante", "Vicealmirante",
    "Servidor Público", "Civil",
]


def listar(con, texto="", solo_activos=False, solo_racion=False):
    sql = "SELECT * FROM personal WHERE 1 = 1"
    parametros = []
    if texto:
        sql += " AND (cedula LIKE ? OR nombres LIKE ? OR unidad LIKE ? OR grado LIKE ?)"
        parametros += [f"%{texto}%"] * 4
    if solo_activos:
        sql += " AND activo = 1"
    if solo_racion:
        sql += " AND racion_institucional = 1"
    return con.execute(sql + " ORDER BY unidad, nombres", parametros).fetchall()


def obtener(con, personal_id):
    fila = con.execute("SELECT * FROM personal WHERE id = ?", (personal_id,)).fetchone()
    if not fila:
        raise ErrorNegocio("La persona no existe.")
    return fila


def por_cedula(con, cedula):
    return con.execute("SELECT * FROM personal WHERE cedula = ?", (str(cedula).strip(),)).fetchone()


def unidades(con):
    return [f[0] for f in con.execute("SELECT DISTINCT unidad FROM personal WHERE unidad <> '' ORDER BY 1")]


def nombre_completo(persona):
    return f"{persona['grado']} {persona['nombres']}".strip()


def guardar(con, datos, personal_id=None):
    cedula = str(datos.get("cedula", "")).strip()
    nombres = str(datos.get("nombres", "")).strip()
    if not cedula:
        raise ErrorNegocio("La cédula o número de identificación es obligatorio.")
    if not nombres:
        raise ErrorNegocio("Los apellidos y nombres son obligatorios.")
    existente = por_cedula(con, cedula)
    if existente and existente["id"] != personal_id:
        raise ErrorNegocio(f"Ya existe una persona con la cédula {cedula}: {existente['nombres']}.")
    limite = r2(datos.get("limite_credito") or 0)
    if limite < 0:
        raise ErrorNegocio("El límite de crédito no puede ser negativo.")
    valores = (
        cedula,
        str(datos.get("grado", "")).strip(),
        nombres,
        str(datos.get("unidad", "")).strip(),
        int(bool(datos.get("racion_institucional", True))),
        int(bool(datos.get("credito", False))),
        limite,
        int(bool(datos.get("activo", True))),
    )
    with con:
        if personal_id:
            con.execute(
                """UPDATE personal SET cedula = ?, grado = ?, nombres = ?, unidad = ?, racion_institucional = ?,
                   credito = ?, limite_credito = ?, activo = ? WHERE id = ?""",
                valores + (personal_id,),
            )
            return personal_id
        return con.execute(
            """INSERT INTO personal(cedula, grado, nombres, unidad, racion_institucional, credito, limite_credito, activo)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            valores,
        ).lastrowid


def _normalizar(texto):
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sin_tildes.strip().lower()


def _leer_texto(ruta):
    with open(ruta, "rb") as f:
        crudo = f.read()
    for codificacion in ("utf-8-sig", "cp1252"):
        try:
            return crudo.decode(codificacion)
        except UnicodeDecodeError:
            pass
    raise ErrorNegocio("No se pudo leer el archivo: codificación desconocida.")


def importar_csv(con, ruta):
    """Importa o actualiza personal desde un CSV con columnas: cedula, grado, nombres, unidad.

    Devuelve (nuevos, actualizados, errores)."""
    contenido = _leer_texto(ruta)
    try:
        dialecto = csv.Sniffer().sniff(contenido[:4096], delimiters=";,\t")
    except csv.Error:
        dialecto = csv.excel
    lector = csv.DictReader(io.StringIO(contenido), dialect=dialecto)
    if not lector.fieldnames or "cedula" not in [_normalizar(c) for c in lector.fieldnames if c]:
        raise ErrorNegocio("El archivo debe tener una fila de encabezados con: cedula, grado, nombres, unidad.")
    nuevos = actualizados = 0
    errores = []
    for numero_fila, fila in enumerate(lector, start=2):
        fila = {_normalizar(k): (v or "").strip() for k, v in fila.items() if k}
        if not any(fila.values()):
            continue
        try:
            existente = por_cedula(con, fila.get("cedula", ""))
            datos = dict(existente) if existente else {"racion_institucional": 1, "activo": 1}
            datos.update({k: fila[k] for k in ("cedula", "grado", "nombres", "unidad") if fila.get(k)})
            guardar(con, datos, existente["id"] if existente else None)
            if existente:
                actualizados += 1
            else:
                nuevos += 1
        except ErrorNegocio as e:
            errores.append(f"Fila {numero_fila}: {e}")
    return nuevos, actualizados, errores


PLANTILLA_CSV = "cedula;grado;nombres;unidad\n0912345678;Cabo Primero;PEREZ LOPEZ JUAN CARLOS;Infantería de Marina\n"
