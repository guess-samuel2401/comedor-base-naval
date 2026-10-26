"""Utilidades comunes: errores, redondeo, números y fechas."""
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal


class ErrorNegocio(Exception):
    """Error de validación que se muestra tal cual al usuario."""


def r2(valor):
    """Redondea a 2 decimales con redondeo comercial (0.005 -> 0.01)."""
    return float(Decimal(str(valor or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def numero(texto, campo="el valor"):
    """Convierte texto a número aceptando coma o punto decimal."""
    if isinstance(texto, (int, float)):
        return float(texto)
    t = str(texto).strip().replace(" ", "").replace("$", "")
    if not t:
        raise ErrorNegocio(f"Ingrese {campo}.")
    if "," in t and "." in t:
        t = t.replace(",", "")  # 1,234.56
    else:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        raise ErrorNegocio(f"{campo[:1].upper()}{campo[1:]} no es un número válido: {texto}") from None


def hoy():
    return date.today().isoformat()


def hora_actual():
    return datetime.now().strftime("%H:%M:%S")


def primer_dia_mes(iso=None):
    d = date.fromisoformat(iso or hoy())
    return d.replace(day=1).isoformat()


def fecha_iso(texto):
    """Convierte dd/mm/aaaa (o aaaa-mm-dd) a aaaa-mm-dd."""
    t = str(texto).strip()
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(t, formato).date().isoformat()
        except ValueError:
            pass
    raise ErrorNegocio(f"Fecha inválida: «{texto}». Use el formato dd/mm/aaaa.")


def fecha_ver(iso):
    """aaaa-mm-dd -> dd/mm/aaaa."""
    if not iso:
        return ""
    try:
        return datetime.strptime(str(iso)[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return str(iso)


def fmt_dinero(valor):
    return f"$ {r2(valor):,.2f}"


def fmt_cant(valor):
    """Cantidad con hasta 3 decimales, sin ceros sobrantes."""
    texto = f"{float(valor or 0):,.3f}".rstrip("0").rstrip(".")
    return "0" if texto in ("-0", "") else texto


def formatear(valor, tipo):
    """Formatea un valor según el tipo de columna de un reporte."""
    if valor is None or valor == "":
        return ""
    if tipo == "dinero":
        return fmt_dinero(valor)
    if tipo == "cant":
        return fmt_cant(valor)
    if tipo == "entero":
        return f"{int(valor):,}"
    if tipo == "fecha":
        return fecha_ver(valor)
    if tipo == "pct":
        return f"{valor:.1f} %"
    return str(valor)
