# Sistema de facturación y costos – Comedor de base naval

Programa de escritorio para Windows que lleva:

- **Raciones institucionales**: lo que el comedor factura a la Armada, por persona y tiempo de comida.
- **Caja**: ventas de contado y a crédito (cobro a fin de mes / descuento en rol), con o sin IVA.
- **Bodega**: insumos, compras, salidas a cocina, mermas y ajustes, con costo promedio ponderado.
- **Reportes**: liquidación de raciones, costos y margen, ventas, consumo, existencias, saldos de crédito.

Es de **control interno**: los comprobantes dicen “No válido como factura” y no se envían al SRI.

## Requisitos e inicio

Solo necesita **Python 3.10 o superior** (no requiere librerías adicionales ni internet).

- Doble clic en **`Iniciar Comedor.bat`**, o
- desde una terminal en esta carpeta: `python main.py`

Los datos se guardan en `datos\comedor.db`. Los comprobantes y reportes impresos se guardan en
`datos\impresiones\` y se abren en el navegador (Ctrl+P para imprimir o guardar como PDF).

## Primeros pasos

1. **Configuración**: nombre del comedor, entidad, tarifa de IVA (15 % por defecto) y **precio por ración**
   de desayuno, almuerzo y merienda (lo que paga la Armada).
2. **Personal**: registre a cada persona con su cédula. Para cargar muchas a la vez use
   *Descargar plantilla CSV* → llénela en Excel → guárdela como CSV → *Importar desde Excel (CSV)*.
   - *Ración pagada por la Armada*: puede registrar raciones institucionales.
   - *Autorizado a crédito* y *límite*: puede consumir en caja y pagar a fin de mes.
3. **Bodega → Existencias**: cree los insumos. Para el inventario con el que arranca, use *Ajustar stock*
   (la primera carga de cada insumo queda como **inventario inicial** y no afecta los costos).
4. **Productos**: lo que se vende en caja. Los platos preparados no se vinculan a bodega; las bebidas y
   snacks sí (cada unidad vendida descuenta una unidad del insumo).

## Uso diario

| Momento | Pestaña | Qué hacer |
|---|---|---|
| Cada comida | **Raciones** | Elegir el tiempo, escribir o escanear la cédula y Enter. Hay registro masivo desde lista. |
| Ventas | **Caja** | Buscar producto, agregar, elegir contado o crédito (con cédula), *Registrar venta* (F12). |
| Llega mercadería | **Bodega → Compras** | Proveedor, N° de factura, insumos con costo **sin IVA** y casilla *Grava IVA*. |
| Se entrega a cocina | **Bodega → Salidas a cocina** | Insumo y cantidad; motivo *Consumo de cocina* o *Merma*. |
| Fin de mes | **Créditos** | *Registrar cobro* por cada descuento de rol; *Estado de cuenta* para entregar. |
| Fin de mes | **Reportes** | *Liquidación de raciones (Armada)* para cobrar a la institución; *Costos y margen*. |

## Cómo se calculan los costos

- **Costo promedio ponderado**: cada compra recalcula el costo unitario del insumo. El IVA pagado en la
  compra forma parte del costo, porque el comedor no lo recupera.
- **Las compras no son costo** hasta que los insumos salen de bodega (cocina, venta o merma).
- *Costos y margen* = ingresos (raciones + ventas sin IVA) − salidas de bodega al costo.
- *Costo promedio por plato* = insumos entregados a cocina ÷ (raciones + platos vendidos).
- En ventas, el precio del producto es el **precio final**; si grava IVA, el comprobante desglosa la base y el IVA.

## Respaldos

En **Configuración → Crear respaldo…** se genera una copia completa de la base de datos. Hágalo cada semana
y guárdela fuera de la computadora. Para restaurar: cierre el programa y reemplace `datos\comedor.db` por el
respaldo.

## Estructura del código

```
main.py                 punto de entrada
comedor/
  db.py                 esquema SQLite, configuración y respaldos
  personal.py           personal y su importación desde CSV
  raciones.py           raciones institucionales
  ventas.py             productos, ventas, anulaciones, crédito y cobros
  inventario.py         insumos, proveedores, compras, salidas, ajustes
  reportes.py           reportes y exportación a CSV
  impresion.py          comprobantes y reportes en HTML para imprimir
  ui/                   interfaz Tkinter (una pestaña por archivo)
tests/                  pruebas de la lógica: python -m unittest discover -s tests -t .
```
