"""Pestaña de bodega: existencias, compras, salidas a cocina y proveedores."""
import tkinter as tk
from datetime import date, timedelta
from tkinter import messagebox, ttk

from .. import db, inventario, raciones, reportes
from ..util import ErrorNegocio, fecha_ver, fmt_cant, fmt_dinero, hoy, numero, primer_dia_mes
from .comun import CampoFecha, Dialogo, Formulario, Selector, Tabla, VistaReporte


def formulario_insumo(padre, con, insumo_id=None):
    valores = dict(inventario.obtener_insumo(con, insumo_id)) if insumo_id else {"activo": True, "unidad": "kg"}
    return Formulario(
        padre, "Editar insumo" if insumo_id else "Nuevo insumo",
        [("nombre", "Nombre", "texto"), ("categoria", "Categoría", "lista", inventario.categorias(con)),
         ("unidad", "Unidad de medida", "lista", inventario.UNIDADES),
         ("stock_minimo", "Stock mínimo (alerta)", "numero"), ("activo", "Activo", "check")],
        valores, al_guardar=lambda d: inventario.guardar_insumo(con, d, insumo_id),
        nota="El stock no se edita aquí: entra con las compras y se corrige con «Ajustar stock».",
    ).mostrar()


def formulario_proveedor(padre, con, proveedor_id=None):
    valores = {}
    if proveedor_id:
        valores = dict(con.execute("SELECT * FROM proveedores WHERE id = ?", (proveedor_id,)).fetchone())
    return Formulario(
        padre, "Editar proveedor" if proveedor_id else "Nuevo proveedor",
        [("nombre", "Nombre / razón social", "texto"), ("ruc", "RUC / cédula", "texto"),
         ("telefono", "Teléfono", "texto"), ("direccion", "Dirección", "texto")],
        valores, al_guardar=lambda d: inventario.guardar_proveedor(con, d, proveedor_id),
    ).mostrar()


class PestanaBodega(ttk.Frame):
    titulo = "Bodega"

    def __init__(self, padre, app):
        super().__init__(padre, padding=8)
        self.app = app
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)
        for clase in (_Existencias, _Compras, _Salidas, _Proveedores):
            sub = clase(self.nb, app)
            self.nb.add(sub, text=sub.titulo)
        self.nb.bind("<<NotebookTabChanged>>", lambda e: self.refrescar())

    def refrescar(self):
        self.nb.nametowidget(self.nb.select()).refrescar()

    def al_mostrar(self):
        self.refrescar()


class _Existencias(ttk.Frame):
    titulo = "Existencias"

    def __init__(self, padre, app):
        super().__init__(padre, padding=8)
        self.con = app.con
        barra = ttk.Frame(self)
        barra.pack(fill="x")
        ttk.Label(barra, text="Buscar:").pack(side="left")
        self.texto = ttk.Entry(barra, width=28)
        self.texto.pack(side="left", padx=6)
        self.texto.bind("<KeyRelease>", lambda e: self.refrescar())
        self.inactivos = tk.BooleanVar()
        ttk.Checkbutton(barra, text="Mostrar inactivos", variable=self.inactivos,
                        command=self.refrescar).pack(side="left", padx=8)
        for texto, comando in (("Kardex…", self._kardex), ("Ajustar stock…", self._ajustar),
                               ("Editar", self._editar), ("Nuevo insumo", self._nuevo)):
            ttk.Button(barra, text=texto, command=comando).pack(side="right", padx=3)
        self.tabla = Tabla(self, [("nombre", "Insumo", 230), ("cat", "Categoría", 130), ("unidad", "Unidad", 70),
                                  ("stock", "Stock", 90, "e"), ("minimo", "Mínimo", 80, "e"),
                                  ("costo", "Costo prom.", 100, "e"), ("valor", "Valor", 110, "e"),
                                  ("estado", "Estado", 110)], alto=20, al_doble_clic=self._editar)
        self.tabla.pack(fill="both", expand=True, pady=8)
        self.lbl = ttk.Label(self, style="Subtitulo.TLabel")
        self.lbl.pack(anchor="e")

    def refrescar(self):
        self.tabla.limpiar()
        valor_total = 0
        bajos = 0
        for i in inventario.insumos(self.con, self.texto.get().strip(), solo_activos=not self.inactivos.get()):
            valor = i["stock"] * i["costo_promedio"]
            valor_total += valor
            bajo = i["stock_minimo"] > 0 and i["stock"] <= i["stock_minimo"]
            bajos += bajo
            estado = "Inactivo" if not i["activo"] else "BAJO MÍNIMO" if bajo else ""
            tags = ("gris",) if not i["activo"] else ("alerta",) if bajo else ()
            self.tabla.agregar((i["nombre"], i["categoria"], i["unidad"], fmt_cant(i["stock"]),
                                fmt_cant(i["stock_minimo"]), f"{i['costo_promedio']:.4f}", fmt_dinero(valor), estado),
                               iid=i["id"], tags=tags)
        self.lbl.config(text=f"Valor del inventario: {fmt_dinero(valor_total)}"
                             + (f"   ·   {bajos} insumo(s) bajo el mínimo" if bajos else ""))

    def _nuevo(self):
        formulario_insumo(self, self.con)
        self.refrescar()

    def _editar(self):
        formulario_insumo(self, self.con, int(self.tabla.requerir("un insumo")))
        self.refrescar()

    def _ajustar(self):
        insumo_id = int(self.tabla.requerir("un insumo"))
        ins = inventario.obtener_insumo(self.con, insumo_id)
        primera = not inventario.tiene_movimientos(self.con, insumo_id)
        campos = [("fecha", "Fecha", "fecha"), ("stock_real", f"Stock real contado ({ins['unidad']})", "numero"),
                  ("costo_unit", "Costo unitario (si aumenta)", "numero"), ("nota", "Motivo", "texto")]
        if not primera:
            campos.append(("inicial", "Es carga de inventario inicial (no afecta costos)", "check"))
        nota = (f"Stock actual en sistema: {fmt_cant(ins['stock'])} {ins['unidad']}. "
                + ("Al ser el primer registro, se tomará como INVENTARIO INICIAL." if primera else
                   "La diferencia se registra como faltante (costo) o sobrante."))
        Formulario(
            self, f"Ajustar stock – {ins['nombre']}", campos,
            {"stock_real": ins["stock"], "costo_unit": ins["costo_promedio"] or None,
             "nota": "Inventario inicial" if primera else "Conteo físico"},
            al_guardar=lambda d: inventario.ajustar_stock(self.con, insumo_id, d["stock_real"], d["nota"], d["fecha"],
                                                          d["costo_unit"], True if primera else d["inicial"]),
            nota=nota,
        ).mostrar()
        self.refrescar()

    def _kardex(self):
        Kardex(self, self.con, int(self.tabla.requerir("un insumo"))).mostrar()


class Kardex(Dialogo):
    def __init__(self, padre, con, insumo_id):
        super().__init__(padre, "Kardex del insumo", redimensionable=True)
        self.con = con
        self.insumo_id = insumo_id
        barra = ttk.Frame(self.cuerpo)
        barra.pack(fill="x")
        ttk.Label(barra, text="Desde:").pack(side="left")
        self.desde = CampoFecha(barra, iso=primer_dia_mes())
        self.desde.pack(side="left", padx=4)
        ttk.Label(barra, text="Hasta:").pack(side="left", padx=(8, 0))
        self.hasta = CampoFecha(barra)
        self.hasta.pack(side="left", padx=4)
        ttk.Button(barra, text="Generar", command=self._generar).pack(side="left", padx=8)
        self.vista = VistaReporte(self.cuerpo, con)
        self.vista.pack(fill="both", expand=True, pady=(8, 0))
        self._generar()

    def _generar(self):
        self.vista.mostrar(reportes.kardex(self.con, self.insumo_id, self.desde.iso(), self.hasta.iso()))


class _Compras(ttk.Frame):
    titulo = "Compras"

    def __init__(self, padre, app):
        super().__init__(padre, padding=8)
        self.con = app.con
        self.lineas = []

        cab = ttk.Frame(self)
        cab.pack(fill="x")
        ttk.Label(cab, text="Fecha:").grid(row=0, column=0, sticky="e")
        self.fecha = CampoFecha(cab)
        self.fecha.grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(cab, text="Proveedor:").grid(row=0, column=2, sticky="e", padx=(12, 0))
        self.proveedor = Selector(cab, buscar=True, width=34)
        self.proveedor.grid(row=0, column=3, sticky="w", padx=4)
        ttk.Button(cab, text="+", width=3, command=self._nuevo_proveedor).grid(row=0, column=4)
        ttk.Label(cab, text="N° factura / nota de venta:").grid(row=0, column=5, sticky="e", padx=(12, 0))
        self.documento = ttk.Entry(cab, width=20)
        self.documento.grid(row=0, column=6, sticky="w", padx=4)

        lin = ttk.LabelFrame(self, text=" Agregar insumo ", padding=8)
        lin.pack(fill="x", pady=8)
        ttk.Label(lin, text="Insumo:").pack(side="left")
        self.insumo = Selector(lin, buscar=True, width=34)
        self.insumo.pack(side="left", padx=4)
        ttk.Button(lin, text="+", width=3, command=self._nuevo_insumo).pack(side="left")
        ttk.Label(lin, text="Cantidad:").pack(side="left", padx=(10, 2))
        self.cantidad = ttk.Entry(lin, width=9)
        self.cantidad.pack(side="left")
        ttk.Label(lin, text="Costo unit. sin IVA:").pack(side="left", padx=(10, 2))
        self.costo = ttk.Entry(lin, width=10)
        self.costo.pack(side="left")
        self.con_iva = tk.BooleanVar()
        ttk.Checkbutton(lin, text="Grava IVA", variable=self.con_iva).pack(side="left", padx=8)
        ttk.Button(lin, text="Agregar", command=self._agregar).pack(side="left")
        for w in (self.cantidad, self.costo):
            w.bind("<Return>", lambda e: self._agregar())

        self.tabla = Tabla(self, [("insumo", "Insumo", 240), ("cant", "Cantidad", 90, "e"), ("unidad", "Unidad", 70),
                                  ("costo", "Costo unit.", 90, "e"), ("iva", "IVA", 50, "center"),
                                  ("total", "Subtotal", 100, "e")], alto=8)
        self.tabla.pack(fill="both", expand=True)
        pie = ttk.Frame(self)
        pie.pack(fill="x", pady=6)
        ttk.Button(pie, text="Quitar línea", command=self._quitar).pack(side="left")
        ttk.Button(pie, text="Guardar compra", style="Grande.TButton", command=self._guardar).pack(side="right")
        self.lbl_totales = ttk.Label(pie, font=("Consolas", 10), justify="right")
        self.lbl_totales.pack(side="right", padx=16)

        rec = ttk.LabelFrame(self, text=" Compras de los últimos 30 días ", padding=6)
        rec.pack(fill="both", expand=True)
        self.recientes = Tabla(rec, [("fecha", "Fecha", 90), ("prov", "Proveedor", 240), ("doc", "Documento", 140),
                                     ("total", "Total", 100, "e")], alto=6, al_doble_clic=self._ver_compra)
        self.recientes.pack(fill="both", expand=True)

    def refrescar(self):
        self.proveedor.cargar([(p["id"], p["nombre"]) for p in inventario.proveedores(self.con)])
        self._insumos = {i["id"]: i for i in inventario.insumos(self.con)}
        self.insumo.cargar([(i["id"], f"{i['nombre']} ({i['unidad']})") for i in self._insumos.values()])
        self.recientes.limpiar()
        desde = (date.today() - timedelta(days=30)).isoformat()
        for c in inventario.compras(self.con, desde, hoy()):
            self.recientes.agregar((fecha_ver(c["fecha"]), c["proveedor"], c["documento"], fmt_dinero(c["total"])),
                                   iid=c["id"])
        self._actualizar()

    def _nuevo_proveedor(self):
        if formulario_proveedor(self, self.con):
            self.refrescar()

    def _nuevo_insumo(self):
        if formulario_insumo(self, self.con):
            self.refrescar()

    def _agregar(self):
        insumo_id = self.insumo.valor()
        if insumo_id is None:
            raise ErrorNegocio("Seleccione un insumo de la lista (o créelo con el botón +).")
        cantidad = numero(self.cantidad.get(), "la cantidad")
        costo = numero(self.costo.get(), "el costo unitario")
        if cantidad <= 0 or costo < 0:
            raise ErrorNegocio("La cantidad debe ser mayor que cero y el costo no puede ser negativo.")
        self.lineas.append({"insumo_id": insumo_id, "cantidad": cantidad, "costo_unit": costo,
                            "aplica_iva": self.con_iva.get()})
        self.insumo.set("")
        self.cantidad.delete(0, "end")
        self.costo.delete(0, "end")
        self.insumo.focus_set()
        self._actualizar()

    def _quitar(self):
        del self.lineas[int(self.tabla.requerir("la línea a quitar"))]
        self._actualizar()

    def _actualizar(self):
        self.tabla.limpiar()
        for n, l in enumerate(self.lineas):
            ins = self._insumos.get(l["insumo_id"]) or inventario.obtener_insumo(self.con, l["insumo_id"])
            self.tabla.agregar((ins["nombre"], fmt_cant(l["cantidad"]), ins["unidad"], f"{l['costo_unit']:.4f}",
                                "Sí" if l["aplica_iva"] else "", f"{l['cantidad'] * l['costo_unit']:.2f}"), iid=n)
        pct = db.iva_pct(self.con)
        t = inventario.totales_compra(self.lineas, pct)
        self.lbl_totales.config(text=f"Subtotal 0%: {t['subtotal_0']:>10.2f}   Subtotal {pct:g}%: "
                                     f"{t['subtotal_iva']:>10.2f}\nIVA: {t['iva']:>10.2f}   "
                                     f"TOTAL: {t['total']:>10.2f}")

    def _guardar(self):
        if not self.lineas:
            raise ErrorNegocio("Agregue al menos un insumo a la compra.")
        if self.proveedor.get().strip() and self.proveedor.valor() is None:
            raise ErrorNegocio("El proveedor no está en la lista. Créelo con el botón + o deje el campo vacío.")
        inventario.registrar_compra(self.con, self.proveedor.valor(), self.documento.get(), self.lineas,
                                    self.fecha.iso())
        total = inventario.totales_compra(self.lineas, db.iva_pct(self.con))["total"]
        self.lineas = []
        self.documento.delete(0, "end")
        self.proveedor.set("")
        self.refrescar()
        messagebox.showinfo("Compra registrada", f"Compra por {fmt_dinero(total)} ingresada a bodega.", parent=self)

    def _ver_compra(self):
        compra_id = int(self.recientes.requerir("una compra"))
        detalle = inventario.detalle_compra(self.con, compra_id)
        texto = "\n".join(f"{fmt_cant(d['cantidad'])} {d['unidad']}  {d['insumo']}  @ {d['costo_unit']:.4f}"
                          f"{' + IVA' if d['aplica_iva'] else ''}  = {d['total']:.2f}" for d in detalle)
        messagebox.showinfo("Detalle de la compra", texto, parent=self)


class _Salidas(ttk.Frame):
    titulo = "Salidas a cocina"

    def __init__(self, padre, app):
        super().__init__(padre, padding=8)
        self.con = app.con
        self.lineas = []

        cab = ttk.Frame(self)
        cab.pack(fill="x")
        ttk.Label(cab, text="Fecha:").pack(side="left")
        self.fecha = CampoFecha(cab)
        self.fecha.pack(side="left", padx=4)
        self.fecha.bind("<Return>", lambda e: self.refrescar())
        ttk.Label(cab, text="Motivo:").pack(side="left", padx=(12, 2))
        self.motivo = Selector(cab, width=22)
        self.motivo.cargar(list(inventario.ORIGENES_SALIDA.items()))
        self.motivo.poner("COCINA")
        self.motivo.pack(side="left")
        ttk.Label(cab, text="Tiempo de comida:").pack(side="left", padx=(12, 2))
        self.tiempo = Selector(cab, width=14)
        self.tiempo.pack(side="left")

        lin = ttk.LabelFrame(self, text=" Agregar insumo ", padding=8)
        lin.pack(fill="x", pady=8)
        ttk.Label(lin, text="Insumo:").pack(side="left")
        self.insumo = Selector(lin, buscar=True, width=42)
        self.insumo.pack(side="left", padx=4)
        ttk.Label(lin, text="Cantidad:").pack(side="left", padx=(10, 2))
        self.cantidad = ttk.Entry(lin, width=9)
        self.cantidad.pack(side="left")
        self.cantidad.bind("<Return>", lambda e: self._agregar())
        ttk.Label(lin, text="Nota:").pack(side="left", padx=(10, 2))
        self.nota = ttk.Entry(lin, width=24)
        self.nota.pack(side="left")
        ttk.Button(lin, text="Agregar", command=self._agregar).pack(side="left", padx=8)

        self.tabla = Tabla(self, [("insumo", "Insumo", 240), ("cant", "Cantidad", 90, "e"), ("unidad", "Unidad", 70),
                                  ("motivo", "Motivo", 150), ("tiempo", "Tiempo", 100), ("nota", "Nota", 200)], alto=7)
        self.tabla.pack(fill="both", expand=True)
        pie = ttk.Frame(self)
        pie.pack(fill="x", pady=6)
        ttk.Button(pie, text="Quitar línea", command=self._quitar).pack(side="left")
        ttk.Button(pie, text="Registrar salidas", style="Grande.TButton", command=self._guardar).pack(side="right")

        reg = ttk.LabelFrame(self, text=" Salidas registradas en la fecha ", padding=6)
        reg.pack(fill="both", expand=True)
        self.registradas = Tabla(reg, [("insumo", "Insumo", 240), ("cant", "Cantidad", 90, "e"),
                                       ("unidad", "Unidad", 70), ("motivo", "Motivo", 150), ("tiempo", "Tiempo", 100),
                                       ("costo", "Costo", 100, "e")], alto=7)
        self.registradas.pack(fill="both", expand=True)
        self.lbl_costo = ttk.Label(reg, style="Subtitulo.TLabel")
        self.lbl_costo.pack(anchor="e")

    def refrescar(self):
        self.tiempo.cargar([(None, "(general)")] + [(t["id"], t["nombre"]) for t in raciones.tiempos(self.con)])
        if not self.tiempo.get():
            self.tiempo.poner(None)
        self._insumos = {i["id"]: i for i in inventario.insumos(self.con)}
        self.insumo.cargar([(i["id"], f"{i['nombre']} ({i['unidad']}) — stock {fmt_cant(i['stock'])}")
                            for i in self._insumos.values()])
        self.registradas.limpiar()
        costo = 0
        for m in inventario.salidas_del_dia(self.con, self.fecha.iso()):
            valor = -m["cantidad"] * m["costo_unit"]
            costo += valor
            self.registradas.agregar((m["insumo"], fmt_cant(-m["cantidad"]), m["unidad"],
                                      inventario.ORIGENES_SALIDA[m["origen"]], m["tiempo"], fmt_dinero(valor)))
        self.lbl_costo.config(text=f"Costo total de salidas del día: {fmt_dinero(costo)}")
        self._actualizar()

    def _agregar(self):
        insumo_id = self.insumo.valor()
        if insumo_id is None:
            raise ErrorNegocio("Seleccione un insumo de la lista.")
        cantidad = numero(self.cantidad.get(), "la cantidad")
        if cantidad <= 0:
            raise ErrorNegocio("La cantidad debe ser mayor que cero.")
        origen = self.motivo.valor() or "COCINA"
        self.lineas.append({"insumo_id": insumo_id, "cantidad": cantidad, "origen": origen,
                            "tiempo_id": self.tiempo.valor(), "nota": self.nota.get().strip()})
        self.insumo.set("")
        self.cantidad.delete(0, "end")
        self.nota.delete(0, "end")
        self.insumo.focus_set()
        self._actualizar()

    def _quitar(self):
        del self.lineas[int(self.tabla.requerir("la línea a quitar"))]
        self._actualizar()

    def _actualizar(self):
        self.tabla.limpiar()
        nombres_tiempo = {t["id"]: t["nombre"] for t in raciones.tiempos(self.con)}
        for n, l in enumerate(self.lineas):
            ins = self._insumos[l["insumo_id"]]
            self.tabla.agregar((ins["nombre"], fmt_cant(l["cantidad"]), ins["unidad"],
                                inventario.ORIGENES_SALIDA[l["origen"]], nombres_tiempo.get(l["tiempo_id"], ""),
                                l["nota"]), iid=n)

    def _guardar(self):
        inventario.registrar_salidas(self.con, self.fecha.iso(), self.lineas)
        self.lineas = []
        self.refrescar()


class _Proveedores(ttk.Frame):
    titulo = "Proveedores"

    def __init__(self, padre, app):
        super().__init__(padre, padding=8)
        self.con = app.con
        barra = ttk.Frame(self)
        barra.pack(fill="x")
        ttk.Label(barra, text="Buscar:").pack(side="left")
        self.texto = ttk.Entry(barra, width=28)
        self.texto.pack(side="left", padx=6)
        self.texto.bind("<KeyRelease>", lambda e: self.refrescar())
        ttk.Button(barra, text="Editar", command=self._editar).pack(side="right", padx=3)
        ttk.Button(barra, text="Nuevo proveedor", command=self._nuevo).pack(side="right", padx=3)
        self.tabla = Tabla(self, [("nombre", "Nombre", 260), ("ruc", "RUC", 130), ("tel", "Teléfono", 120),
                                  ("dir", "Dirección", 300)], alto=20, al_doble_clic=self._editar)
        self.tabla.pack(fill="both", expand=True, pady=8)

    def refrescar(self):
        self.tabla.limpiar()
        for p in inventario.proveedores(self.con, self.texto.get().strip()):
            self.tabla.agregar((p["nombre"], p["ruc"], p["telefono"], p["direccion"]), iid=p["id"])

    def _nuevo(self):
        formulario_proveedor(self, self.con)
        self.refrescar()

    def _editar(self):
        formulario_proveedor(self, self.con, int(self.tabla.requerir("un proveedor")))
        self.refrescar()
