"""Pestaña de configuración: datos del comedor, IVA, precios de raciones y respaldos."""
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from .. import db, raciones
from ..util import ErrorNegocio, numero
from .comun import texto_dinero, texto_numero


class PestanaConfig(ttk.Frame):
    titulo = "Configuración"

    def __init__(self, padre, app):
        super().__init__(padre, padding=16)
        self.app = app
        self.con = app.con

        datos = ttk.LabelFrame(self, text=" Datos del comedor ", padding=12)
        datos.pack(fill="x")
        self.campos = {}
        for fila, (clave, etiqueta) in enumerate((("nombre_comedor", "Nombre del comedor"),
                                                  ("entidad", "Entidad / base naval"),
                                                  ("direccion", "Dirección"),
                                                  ("iva_pct", "Tarifa de IVA (%)"))):
            ttk.Label(datos, text=etiqueta + ":").grid(row=fila, column=0, sticky="e", padx=(0, 8), pady=3)
            e = ttk.Entry(datos, width=50 if clave != "iva_pct" else 8)
            e.grid(row=fila, column=1, sticky="w", pady=3)
            self.campos[clave] = e
        ttk.Label(datos, text="El IVA se aplica solo a los productos y compras marcados «Grava IVA».",
                  foreground="#555").grid(row=3, column=2, sticky="w", padx=8)

        prec = ttk.LabelFrame(self, text=" Precio por ración institucional (lo que se factura a la Armada) ", padding=12)
        prec.pack(fill="x", pady=12)
        self.precios = {}
        for col, t in enumerate(raciones.tiempos(self.con)):
            ttk.Label(prec, text=f"{t['nombre']}: $").grid(row=0, column=col * 2, sticky="e", padx=(12 if col else 0, 2))
            e = ttk.Entry(prec, width=9)
            e.grid(row=0, column=col * 2 + 1, sticky="w")
            self.precios[t["id"]] = (t["nombre"], e)
        ttk.Label(prec, foreground="#555", text="Un cambio de precio solo afecta a las raciones que se registren "
                                                "desde ahora; las ya registradas conservan su precio.").grid(
            row=1, column=0, columnspan=8, sticky="w", pady=(8, 0))

        ttk.Button(self, text="Guardar configuración", style="Grande.TButton", command=self._guardar).pack(anchor="w")

        resp = ttk.LabelFrame(self, text=" Respaldo de la información ", padding=12)
        resp.pack(fill="x", pady=16)
        ttk.Label(resp, text=f"Base de datos: {db.RUTA_DB}", foreground="#555").pack(anchor="w")
        ttk.Label(resp, text="Haga un respaldo al menos una vez por semana y guárdelo en una memoria USB o en otra "
                             "computadora.", wraplength=800, justify="left").pack(anchor="w", pady=6)
        ttk.Button(resp, text="Crear respaldo…", command=self._respaldar).pack(anchor="w")

    def refrescar(self):
        for clave, e in self.campos.items():
            e.delete(0, "end")
            e.insert(0, db.config(self.con, clave))
        for t in raciones.tiempos(self.con):
            if t["id"] in self.precios:
                e = self.precios[t["id"]][1]
                e.delete(0, "end")
                e.insert(0, texto_dinero(t["precio_racion"]))

    def _guardar(self):
        valores = {clave: e.get().strip() for clave, e in self.campos.items()}
        if not valores["nombre_comedor"]:
            raise ErrorNegocio("Ingrese el nombre del comedor.")
        iva = numero(valores["iva_pct"], "la tarifa de IVA")
        if not 0 <= iva < 100:
            raise ErrorNegocio("La tarifa de IVA debe estar entre 0 y 100.")
        valores["iva_pct"] = texto_numero(iva, 2)
        precios = {tid: numero(e.get() or 0, f"el precio de {nombre.lower()}") for tid, (nombre, e) in self.precios.items()}
        raciones.guardar_precios(self.con, precios)
        db.guardar_config(self.con, valores)
        self.app.actualizar_encabezado()
        self.refrescar()
        messagebox.showinfo("Configuración", "Configuración guardada.", parent=self)

    def _respaldar(self):
        ruta = filedialog.asksaveasfilename(
            parent=self, title="Guardar respaldo", defaultextension=".db",
            initialfile=f"comedor_respaldo_{datetime.now():%Y%m%d_%H%M}.db", filetypes=[("Respaldo", "*.db")])
        if ruta:
            db.respaldar(self.con, ruta)
            messagebox.showinfo("Respaldo", f"Respaldo creado en:\n{ruta}\n\nPara restaurarlo, cierre el programa y "
                                            f"reemplace el archivo:\n{db.RUTA_DB}", parent=self)

    def al_mostrar(self):
        self.refrescar()
