"""Pestaña de productos de venta (menú, bebidas, snacks)."""
import tkinter as tk
from tkinter import ttk

from .. import inventario, ventas
from ..util import fmt_dinero
from .comun import Formulario, Tabla


class PestanaProductos(ttk.Frame):
    titulo = "Productos"

    def __init__(self, padre, app):
        super().__init__(padre, padding=10)
        self.con = app.con
        barra = ttk.Frame(self)
        barra.pack(fill="x")
        ttk.Label(barra, text="Buscar:").pack(side="left")
        self.texto = ttk.Entry(barra, width=30)
        self.texto.pack(side="left", padx=6)
        self.texto.bind("<KeyRelease>", lambda e: self.refrescar())
        self.inactivos = tk.BooleanVar()
        ttk.Checkbutton(barra, text="Mostrar inactivos", variable=self.inactivos,
                        command=self.refrescar).pack(side="left", padx=8)
        ttk.Button(barra, text="Editar", command=self._editar).pack(side="right", padx=3)
        ttk.Button(barra, text="Nuevo producto", command=self._nuevo).pack(side="right", padx=3)
        self.tabla = Tabla(self, [("codigo", "Código", 80), ("nombre", "Producto", 240), ("cat", "Categoría", 120),
                                  ("precio", "Precio (PVP)", 100, "e"), ("iva", "Grava IVA", 80, "center"),
                                  ("insumo", "Descuenta de bodega", 220), ("estado", "Estado", 80)],
                           alto=22, al_doble_clic=self._editar)
        self.tabla.pack(fill="both", expand=True, pady=8)
        ttk.Label(self, foreground="#555", text=(
            "Los platos preparados (desayuno, almuerzo…) no se vinculan a bodega: su costo sale de las «Salidas a "
            "cocina». Vincule a un insumo solo los productos que se venden tal cual se compran (bebidas, snacks)."
        ), wraplength=900, justify="left").pack(anchor="w")

    def refrescar(self):
        self.tabla.limpiar()
        for p in ventas.productos(self.con, self.texto.get().strip(), solo_activos=not self.inactivos.get()):
            self.tabla.agregar((p["codigo"] or "", p["nombre"], p["categoria"], fmt_dinero(p["precio"]),
                                "Sí" if p["aplica_iva"] else "", p["insumo"] or "",
                                "Activo" if p["activo"] else "Inactivo"),
                               iid=p["id"], tags=() if p["activo"] else ("gris",))

    def _formulario(self, producto_id=None):
        valores = dict(ventas.obtener_producto(self.con, producto_id)) if producto_id else {"activo": True}
        opciones_insumo = [(None, "(ninguno – plato preparado)")] + [
            (i["id"], f"{i['nombre']} ({i['unidad']})") for i in inventario.insumos(self.con)]
        Formulario(
            self, "Editar producto" if producto_id else "Nuevo producto",
            [("codigo", "Código (opcional)", "texto"), ("nombre", "Nombre", "texto"),
             ("categoria", "Categoría", "lista", ventas.categorias(self.con)),
             ("precio", "Precio de venta final (PVP)", "dinero"),
             ("aplica_iva", "Grava IVA (el IVA está incluido en el precio)", "check"),
             ("insumo_id", "Descuenta de bodega", "selector", opciones_insumo), ("activo", "Activo", "check")],
            valores, al_guardar=lambda d: ventas.guardar_producto(self.con, d, producto_id),
            nota="Al vender 1 unidad del producto se descuenta 1 unidad del insumo vinculado.",
        ).mostrar()
        self.refrescar()

    def _nuevo(self):
        self._formulario()

    def _editar(self):
        self._formulario(int(self.tabla.requerir("un producto")))

    def al_mostrar(self):
        self.refrescar()
