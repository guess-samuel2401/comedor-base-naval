"""Comprobantes y reportes en HTML, que se abren en el navegador para imprimir o guardar como PDF."""
import re
import webbrowser
from datetime import datetime
from html import escape

from . import db, ventas
from .util import fecha_ver, fmt_cant

ESTILO = """
body { font-family: "Segoe UI", Arial, sans-serif; color: #111; margin: 24px; }
h1 { font-size: 18px; margin: 0; }
h2 { font-size: 15px; margin: 14px 0 2px; }
.sub { color: #555; font-size: 12px; margin: 2px 0; }
table { border-collapse: collapse; width: 100%; margin-top: 12px; font-size: 12px; }
th, td { border: 1px solid #bbb; padding: 4px 6px; }
th { background: #e8eef5; text-align: left; }
td.n, th.n { text-align: right; white-space: nowrap; }
tr.total td { font-weight: bold; background: #f3f3f3; }
.resumen { margin-top: 14px; font-size: 13px; }
.resumen td { border: none; padding: 2px 8px 2px 0; }
.firmas { display: flex; gap: 60px; margin-top: 70px; font-size: 12px; }
.firmas div { border-top: 1px solid #333; padding-top: 4px; width: 220px; text-align: center; }
.acciones { margin-bottom: 16px; }
.acciones button { font-size: 14px; padding: 6px 16px; cursor: pointer; }
.pie { color: #777; font-size: 11px; margin-top: 20px; }
@media print { .acciones { display: none; } body { margin: 0; } }
"""

ESTILO_TICKET = """
@page { size: 80mm auto; margin: 3mm; }
body { font-family: Consolas, "Courier New", monospace; font-size: 12px; width: 72mm; margin: 8px auto; color: #000; }
.c { text-align: center; } .n { text-align: right; } .b { font-weight: bold; }
table { width: 100%; border-collapse: collapse; }
td { padding: 1px 0; vertical-align: top; }
hr { border: none; border-top: 1px dashed #000; margin: 6px 0; }
.grande { font-size: 15px; }
.acciones { text-align: center; margin-bottom: 10px; }
@media print { .acciones { display: none; } }
"""


def _pagina(titulo, cuerpo, estilo=ESTILO):
    return (f"<!doctype html><html lang='es'><head><meta charset='utf-8'><title>{escape(titulo)}</title>"
            f"<style>{estilo}</style></head><body>"
            "<div class='acciones'><button onclick='window.print()'>Imprimir / Guardar PDF</button></div>"
            f"{cuerpo}</body></html>")


def html_reporte(con, reporte, firmas=None):
    enc = db.encabezado(con)
    numericas = {i for i, c in enumerate(reporte.columnas) if c[1] in ("dinero", "cant", "entero", "pct")}

    def fila_html(valores, clase=""):
        celdas = "".join(f"<td{' class=n' if i in numericas else ''}>{escape(str(v))}</td>"
                         for i, v in enumerate(valores))
        return f"<tr{f' class={clase}' if clase else ''}>{celdas}</tr>"

    encabezados = "".join(f"<th{' class=n' if i in numericas else ''}>{escape(c[0])}</th>"
                          for i, c in enumerate(reporte.columnas))
    filas = "".join(fila_html(f) for f in reporte.filas_formateadas())
    if reporte.totales:
        filas += fila_html(reporte.totales_formateados(), "total")
    resumen = ""
    if reporte.resumen:
        resumen = "<table class='resumen'>" + "".join(
            f"<tr><td>{escape(e)}</td><td><b>{escape(t)}</b></td></tr>" for e, t in reporte.resumen) + "</table>"
    bloque_firmas = ""
    if firmas:
        bloque_firmas = "<div class='firmas'>" + "".join(f"<div>{escape(f)}</div>" for f in firmas) + "</div>"
    cuerpo = (f"<h1>{escape(enc['nombre_comedor'])}</h1>"
              f"<p class='sub'>{escape(enc['entidad'])}{' · ' + escape(enc['direccion']) if enc['direccion'] else ''}</p>"
              f"<h2>{escape(reporte.titulo)}</h2><p class='sub'>{escape(reporte.subtitulo)}</p>"
              f"<table><thead><tr>{encabezados}</tr></thead><tbody>{filas}</tbody></table>"
              f"{resumen}{bloque_firmas}"
              f"<p class='pie'>Generado el {datetime.now():%d/%m/%Y %H:%M}</p>")
    return _pagina(reporte.titulo, cuerpo)


def comprobante_venta(con, venta_id):
    venta, detalle = ventas.obtener(con, venta_id)
    enc = db.encabezado(con)
    lineas = "".join(
        f"<tr><td>{fmt_cant(d['cantidad'])} x {escape(d['descripcion'])}{' *' if d['aplica_iva'] else ''}"
        f"<br>&nbsp;&nbsp;@ {d['precio']:.2f}</td><td class='n'>{d['total']:.2f}</td></tr>"
        for d in detalle
    )
    pct = f"{venta['iva_pct']:g}"
    anulada = f"<p class='c b grande'>*** ANULADA ***<br>{escape(venta['motivo_anulacion'])}</p>" if venta["anulada"] else ""
    cuerpo = f"""
<div class='c b'>{escape(enc['nombre_comedor'])}</div>
<div class='c'>{escape(enc['entidad'])}</div>
{f"<div class='c'>{escape(enc['direccion'])}</div>" if enc['direccion'] else ''}
<hr>
<div class='c b'>COMPROBANTE DE VENTA N° {venta['numero']:06d}</div>
<div>Fecha: {fecha_ver(venta['fecha'])} {venta['hora'][:5]}</div>
<div>Cliente: {escape(venta['cliente'])}</div>
<div>Pago: {ventas.FORMAS_PAGO[venta['forma_pago']]}</div>
{anulada}
<hr>
<table>{lineas}</table>
<hr>
<table>
<tr><td>Subtotal 0%</td><td class='n'>{venta['subtotal_0']:.2f}</td></tr>
<tr><td>Subtotal {pct}%</td><td class='n'>{venta['base_iva']:.2f}</td></tr>
<tr><td>IVA {pct}%</td><td class='n'>{venta['iva']:.2f}</td></tr>
<tr class='b grande'><td>TOTAL USD</td><td class='n'>{venta['total']:.2f}</td></tr>
</table>
<hr>
{"<div>* Producto grava IVA</div>" if any(d['aplica_iva'] for d in detalle) else ""}
{"<br><br><div class='c'>______________________<br>Firma de aceptación del consumo</div>" if venta['forma_pago'] == 'CREDITO' else ""}
<div class='c'>Documento de control interno.<br>No válido como factura.</div>
"""
    return _pagina(f"Venta {venta['numero']}", cuerpo, ESTILO_TICKET)


def abrir(html, nombre):
    """Guarda el HTML en datos/impresiones y lo abre en el navegador predeterminado."""
    seguro = re.sub(r"[^\w\-]+", "_", nombre, flags=re.UNICODE).strip("_") or "documento"
    ruta = db.carpeta_impresiones() / f"{seguro}.html"
    ruta.write_text(html, encoding="utf-8")
    webbrowser.open(ruta.as_uri())
    return ruta
