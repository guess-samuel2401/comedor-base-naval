"""Pestaña de caja: ventas de contado y a crédito."""
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from .. import db, impresion, personal, ventas
from ..util import ErrorNegocio, fecha_ver, fmt_cant, fmt_dinero, hoy, numero
from .comun import COLOR_ERROR, BuscarPersona, CampoFecha, Tabla, mensaje_saldo


class PestanaCaja(ttk.Frame):
    titulo = "Caja"

    def __init__(self, padre, app):
        super().__init__(padre, padding=8)
        self.app = app
        self.con = app.con
        self.lineas = []
        self.persona = None
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)
        self.f_nueva = ttk.Frame(self.nb, padding=8)
        self.f_lista = ttk.Frame(self.nb, padding=8)
        self.nb.add(self.f_nueva, text="Nueva venta")
        self.nb.add(self.f_lista, text="Ventas registradas")
        self._armar_nueva(self.f_nueva)
        self._armar_lista(self.f_lista)
        self.nb.bind("<<NotebookTabChanged>>", lambda e: self.refrescar())
        app.bind("<F12>", lambda e: self._registrar() if self.f_nueva.winfo_ismapped() else None)

    # --- Nueva venta -------------------------------------------------------------

    def _armar_nueva(self, f):
        f.columnconfigure(0, weight=5)
        f.columnconfigure(1, weight=4)
        f.rowconfigure(0, weight=1)
        izq = ttk.LabelFrame(f, text=" Productos ", padding=8)
        izq.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        der = ttk.LabelFrame(f, text=" Venta actual ", padding=8)
        der.grid(row=0, column=1, sticky="nsew")

        b = ttk.Frame(izq)
        b.pack(fill="x")
        ttk.Label(b, text="Buscar:").pack(side="left")
        self.buscar = ttk.Entry(b)
        self.buscar.pack(side="left", fill="x", expand=True, padx=4)
        self.buscar.bind("<KeyRelease>", self._tecla_buscar)
        self.buscar.bind("<Return>", lambda e: self._agregar_desde_busqueda())
        ttk.Label(b, text="Cantidad:").pack(side="left", padx=(10, 2))
        self.cant = ttk.Spinbox(b, from_=1, to=999, width=6)
        self.cant.set(1)
        self.cant.pack(side="left")
        self.tabla_prod = Tabla(izq, [("codigo", "Código", 70), ("nombre", "Producto", 230), ("cat", "Categoría", 100),
                                      ("precio", "Precio", 80, "e"), ("iva", "IVA", 45, "center"),
                                      ("stock", "Stock", 60, "e")], alto=18, al_doble_clic=self._agregar_sel)
        self.tabla_prod.pack(fill="both", expand=True, pady=6)
        pie = ttk.Frame(izq)
        pie.pack(fill="x")
        ttk.Label(pie, text="Doble clic o Enter para agregar.", foreground="#555").pack(side="left")
        ttk.Button(pie, text="Agregar a la venta  →", command=self._agregar_sel).pack(side="right")

        self.tabla_venta = Tabla(der, [("desc", "Descripción", 200), ("cant", "Cant.", 55, "e"),
                                       ("precio", "Precio", 75, "e"), ("total", "Total", 85, "e")], alto=5)
        self.tabla_venta.arbol.bind("<Delete>", lambda e: self._quitar())
        bl = ttk.Frame(der)
        ttk.Button(bl, text="Quitar línea", command=self._quitar).pack(side="left")
        ttk.Button(bl, text="Vaciar", command=self._limpiar).pack(side="left", padx=4)
        self.lbl_totales = ttk.Label(bl, justify="right", font=("Consolas", 10))
        self.lbl_totales.pack(side="right")
        self.lbl_total = ttk.Label(der, font=("Segoe UI", 22, "bold"), anchor="e")

        pago = ttk.LabelFrame(der, text=" Cliente y forma de pago ", padding=8)
        pago.columnconfigure(2, weight=1)
        self.forma = tk.StringVar(value="CONTADO")
        fp = ttk.Frame(pago)
        fp.grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Radiobutton(fp, text="Contado", value="CONTADO", variable=self.forma,
                        command=self._cambio_forma).pack(side="left")
        ttk.Radiobutton(fp, text="Crédito (se cobra a fin de mes)", value="CREDITO", variable=self.forma,
                        command=self._cambio_forma).pack(side="left", padx=12)
        ttk.Label(pago, text="Cédula:").grid(row=1, column=0, sticky="e", pady=3)
        self.cedula = ttk.Entry(pago, width=16)
        self.cedula.grid(row=1, column=1, sticky="w", padx=4)
        self.cedula.bind("<Return>", lambda e: self._buscar_cedula())
        self.cedula.bind("<FocusOut>", lambda e: self._buscar_cedula())
        ttk.Button(pago, text="Buscar…", command=self._buscar_persona).grid(row=1, column=2, sticky="w")
        self.lbl_persona = tk.Label(pago, anchor="w", justify="left", wraplength=380)
        self.lbl_persona.grid(row=2, column=0, columnspan=3, sticky="we")
        ttk.Label(pago, text="Nombre:").grid(row=3, column=0, sticky="e", pady=3)
        self.cliente = ttk.Entry(pago)
        self.cliente.grid(row=3, column=1, columnspan=2, sticky="we", padx=4)
        ttk.Label(pago, text="(opcional; vacío = Consumidor final)", foreground="#555").grid(
            row=4, column=1, columnspan=2, sticky="w", padx=4)
        boton = ttk.Button(der, text="Registrar venta  (F12)", style="Grande.TButton", command=self._registrar)

        # De abajo hacia arriba, para que el botón y el pago siempre queden visibles.
        boton.pack(side="bottom", fill="x", ipady=6)
        pago.pack(side="bottom", fill="x", pady=6)
        self.lbl_total.pack(side="bottom", fill="x")
        bl.pack(side="bottom", fill="x", pady=4)
        self.tabla_venta.pack(fill="both", expand=True)
        self._actualizar_venta()

    def _tecla_buscar(self, evento):
        if evento.keysym == "Down":
            self.tabla_prod.enfocar_primero()
        elif evento.keysym != "Return":
            self._cargar_productos()

    def _cargar_productos(self):
        self._productos = {p["id"]: p for p in ventas.productos(self.con, self.buscar.get().strip())}
        self.tabla_prod.limpiar()
        for p in self._productos.values():
            stock = fmt_cant(p["stock"]) if p["insumo_id"] else ""
            tags = ("alerta",) if p["insumo_id"] and (p["stock"] or 0) <= 0 else ()
            self.tabla_prod.agregar((p["codigo"] or "", p["nombre"], p["categoria"], f"{p['precio']:.2f}",
                                     "Sí" if p["aplica_iva"] else "", stock), iid=p["id"], tags=tags)

    def _cantidad(self):
        cantidad = numero(self.cant.get(), "la cantidad")
        if cantidad <= 0:
            raise ErrorNegocio("La cantidad debe ser mayor que cero.")
        return cantidad

    def _agregar(self, producto_id):
        p = self._productos[producto_id]
        cantidad = self._cantidad()
        for linea in self.lineas:
            if linea["producto_id"] == producto_id:
                linea["cantidad"] += cantidad
                break
        else:
            self.lineas.append({"producto_id": producto_id, "descripcion": p["nombre"], "cantidad": cantidad,
                                "precio": p["precio"], "aplica_iva": bool(p["aplica_iva"])})
        self.cant.set(1)
        self._actualizar_venta()

    def _agregar_sel(self):
        self._agregar(int(self.tabla_prod.requerir("un producto")))

    def _agregar_desde_busqueda(self):
        texto = self.buscar.get().strip().lower()
        exacto = [pid for pid, p in self._productos.items() if (p["codigo"] or "").lower() == texto]
        candidatos = exacto or list(self._productos)
        if len(candidatos) == 1:
            self._agregar(candidatos[0])
            self.buscar.delete(0, "end")
            self._cargar_productos()
        else:
            self.tabla_prod.enfocar_primero()

    def _quitar(self):
        iid = self.tabla_venta.requerir("la línea a quitar")
        del self.lineas[int(iid)]
        self._actualizar_venta()

    def _actualizar_venta(self):
        self.tabla_venta.limpiar()
        for i, l in enumerate(self.lineas):
            l["total"] = round(l["cantidad"] * l["precio"], 2)
            self.tabla_venta.agregar((l["descripcion"] + (" *" if l["aplica_iva"] else ""), fmt_cant(l["cantidad"]),
                                      f"{l['precio']:.2f}", f"{l['total']:.2f}"), iid=i)
        pct = db.iva_pct(self.con)
        t = ventas.calcular_totales(self.lineas, pct)
        self.lbl_totales.config(text=f"Subtotal 0%: {t['subtotal_0']:>9.2f}\n"
                                     f"Subtotal {pct:g}%: {t['base_iva']:>8.2f}\n"
                                     f"IVA {pct:g}%: {t['iva']:>13.2f}")
        self.lbl_total.config(text=f"TOTAL  {fmt_dinero(t['total'])}")

    def _cambio_forma(self):
        if self.forma.get() == "CREDITO":
            self.cedula.focus_set()

    def _poner_persona(self, persona):
        self.persona = persona
        if not persona:
            self.lbl_persona.config(text="")
            return
        texto = f"{personal.nombre_completo(persona)} · {persona['unidad']}"
        color = "#222"
        if persona["credito"]:
            texto += "\n" + mensaje_saldo(ventas.saldo_credito(self.con, persona["id"]), persona["limite_credito"])
        else:
            texto += "\nNo autorizado a crédito (solo contado)."
            color = COLOR_ERROR
        self.lbl_persona.config(text=texto, fg=color)
        self.cliente.delete(0, "end")
        self.cliente.insert(0, personal.nombre_completo(persona))

    def _buscar_cedula(self):
        cedula = self.cedula.get().strip()
        if not cedula:
            if self.persona:
                self._poner_persona(None)
            return
        if self.persona and self.persona["cedula"] == cedula:
            return
        persona = personal.por_cedula(self.con, cedula)
        if not persona:
            self.persona = None
            self.lbl_persona.config(text=f"No existe personal con cédula {cedula}.", fg=COLOR_ERROR)
            return
        self._poner_persona(persona)

    def _buscar_persona(self):
        pid = BuscarPersona(self, self.con, solo_credito=self.forma.get() == "CREDITO").mostrar()
        if pid:
            persona = personal.obtener(self.con, pid)
            self.cedula.delete(0, "end")
            self.cedula.insert(0, persona["cedula"])
            self._poner_persona(persona)

    def _registrar(self):
        self._buscar_cedula()
        if self.cedula.get().strip() and not self.persona:
            raise ErrorNegocio("La cédula ingresada no corresponde a ninguna persona registrada.")
        venta_id = ventas.registrar_venta(self.con, self.lineas, self.forma.get(),
                                          personal_id=self.persona["id"] if self.persona else None,
                                          cliente=self.cliente.get())
        venta, _ = ventas.obtener(self.con, venta_id)
        self._limpiar()
        self._cargar_productos()
        if messagebox.askyesno("Venta registrada",
                               f"Venta N° {venta['numero']} por {fmt_dinero(venta['total'])} "
                               f"({ventas.FORMAS_PAGO[venta['forma_pago']].lower()}).\n\n¿Imprimir comprobante?",
                               parent=self):
            impresion.abrir(impresion.comprobante_venta(self.con, venta_id), f"venta_{venta['numero']}")
        self.buscar.focus_set()

    def _limpiar(self):
        self.lineas = []
        self.forma.set("CONTADO")
        self.cedula.delete(0, "end")
        self.cliente.delete(0, "end")
        self._poner_persona(None)
        self._actualizar_venta()

    # --- Ventas registradas ------------------------------------------------------

    def _armar_lista(self, f):
        barra = ttk.Frame(f)
        barra.pack(fill="x")
        ttk.Label(barra, text="Desde:").pack(side="left")
        self.desde = CampoFecha(barra)
        self.desde.pack(side="left", padx=4)
        ttk.Label(barra, text="Hasta:").pack(side="left", padx=(8, 0))
        self.hasta = CampoFecha(barra)
        self.hasta.pack(side="left", padx=4)
        ttk.Button(barra, text="Buscar", command=self._buscar_ventas).pack(side="left", padx=8)
        self.tabla_ventas = Tabla(f, [("numero", "N°", 70, "e"), ("fecha", "Fecha", 90), ("hora", "Hora", 60),
                                      ("cliente", "Cliente", 260), ("forma", "Pago", 80), ("total", "Total", 90, "e"),
                                      ("estado", "Estado", 220)], alto=18, al_doble_clic=self._ver)
        self.tabla_ventas.pack(fill="both", expand=True, pady=6)
        pie = ttk.Frame(f)
        pie.pack(fill="x")
        ttk.Button(pie, text="Ver / imprimir comprobante", command=self._ver).pack(side="left")
        ttk.Button(pie, text="Anular venta…", command=self._anular).pack(side="left", padx=6)
        self.lbl_resumen = ttk.Label(pie, style="Subtitulo.TLabel")
        self.lbl_resumen.pack(side="right")

    def _buscar_ventas(self):
        filas = ventas.listar_ventas(self.con, self.desde.iso(), self.hasta.iso())
        self.tabla_ventas.limpiar()
        contado = credito = 0
        for v in filas:
            if v["anulada"]:
                estado, tags = f"ANULADA – {v['motivo_anulacion']}", ("gris",)
            else:
                estado, tags = "Válida", ()
                if v["forma_pago"] == "CONTADO":
                    contado += v["total"]
                else:
                    credito += v["total"]
            self.tabla_ventas.agregar((v["numero"], fecha_ver(v["fecha"]), v["hora"][:5], v["cliente"], ventas.FORMAS_PAGO[v["forma_pago"]],
                                       f"{v['total']:.2f}", estado), iid=v["id"], tags=tags)
        self.lbl_resumen.config(text=f"Contado: {fmt_dinero(contado)}   ·   Crédito: {fmt_dinero(credito)}")

    def _ver(self):
        venta_id = int(self.tabla_ventas.requerir("una venta"))
        venta, _ = ventas.obtener(self.con, venta_id)
        impresion.abrir(impresion.comprobante_venta(self.con, venta_id), f"venta_{venta['numero']}")

    def _anular(self):
        venta_id = int(self.tabla_ventas.requerir("una venta"))
        venta, _ = ventas.obtener(self.con, venta_id)
        if venta["anulada"]:
            raise ErrorNegocio("Esa venta ya está anulada.")
        motivo = simpledialog.askstring(
            "Anular venta", f"Venta N° {venta['numero']} – {venta['cliente']} – {fmt_dinero(venta['total'])}\n\n"
                            "Motivo de la anulación:", parent=self)
        if motivo is None:
            return
        ventas.anular_venta(self.con, venta_id, motivo)
        self._buscar_ventas()

    def refrescar(self):
        if self.nb.index("current") == 1:
            self._buscar_ventas()
        else:
            self._cargar_productos()
            self._actualizar_venta()

    def al_mostrar(self):
        self.refrescar()
        if self.nb.index("current") == 0:
            self.buscar.focus_set()
        if self.hasta.iso() < hoy():
            self.hasta.poner(hoy())
