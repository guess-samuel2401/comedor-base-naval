"""Pestaña de registro de raciones institucionales."""
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from .. import personal, raciones
from ..util import ErrorNegocio, fmt_dinero
from .comun import COLOR_ERROR, COLOR_OK, BuscarPersona, CampoFecha, Selector, Tabla


class PestanaRaciones(ttk.Frame):
    titulo = "Raciones"

    def __init__(self, padre, app):
        super().__init__(padre, padding=10)
        self.app = app
        self.con = app.con

        barra = ttk.Frame(self)
        barra.pack(fill="x")
        ttk.Label(barra, text="Fecha:").pack(side="left")
        self.fecha = CampoFecha(barra)
        self.fecha.pack(side="left", padx=(4, 14))
        self.fecha.bind("<Return>", lambda e: self.refrescar())
        ttk.Label(barra, text="Tiempo de comida:").pack(side="left")
        self.tiempo = Selector(barra, width=14)
        self.tiempo.pack(side="left", padx=4)
        self.tiempo.bind("<<ComboboxSelected>>", lambda e: self._cambio_tiempo())
        self.lbl_precio = ttk.Label(barra, foreground="#555")
        self.lbl_precio.pack(side="left", padx=8)
        ttk.Button(barra, text="Actualizar", command=self.refrescar).pack(side="left", padx=8)

        reg = ttk.LabelFrame(self, text=" Registrar ración: escriba o escanee la cédula y presione Enter ", padding=10)
        reg.pack(fill="x", pady=10)
        self.cedula = ttk.Entry(reg, font=("Segoe UI", 18), width=16)
        self.cedula.pack(side="left")
        self.cedula.bind("<Return>", lambda e: self._registrar())
        ttk.Button(reg, text="Registrar", command=self._registrar).pack(side="left", padx=6)
        ttk.Button(reg, text="Buscar persona…", command=self._buscar).pack(side="left")
        ttk.Button(reg, text="Registrar varios desde lista…", command=self._desde_lista).pack(side="left", padx=6)
        self.mensaje = tk.Label(reg, font=("Segoe UI", 13, "bold"), anchor="w", justify="left", wraplength=520)
        self.mensaje.pack(side="left", fill="x", expand=True, padx=12)

        self.tabla = Tabla(self, [("hora", "Hora", 70, "center"), ("cedula", "Cédula", 110), ("grado", "Grado", 140),
                                  ("nombres", "Apellidos y nombres", 300), ("unidad", "Unidad", 180),
                                  ("precio", "Valor", 90, "e")], alto=14, seleccion="extended")
        self.tabla.pack(fill="both", expand=True)
        self.tabla.arbol.bind("<Delete>", lambda e: self._quitar())

        pie = ttk.Frame(self)
        pie.pack(fill="x", pady=(6, 0))
        ttk.Button(pie, text="Quitar seleccionados", command=self._quitar).pack(side="left")
        self.lbl_total = ttk.Label(pie, style="Subtitulo.TLabel")
        self.lbl_total.pack(side="right")
        self.lbl_dia = ttk.Label(pie, foreground="#555")
        self.lbl_dia.pack(side="right", padx=24)

        self._cargar_tiempos()
        self._tiempo_por_hora()

    def _cargar_tiempos(self):
        self._tiempos = {t["id"]: t for t in raciones.tiempos(self.con)}
        self.tiempo.cargar([(t["id"], t["nombre"]) for t in self._tiempos.values()])

    def _tiempo_por_hora(self):
        hora = datetime.now().hour
        orden = 1 if hora < 10 else 2 if hora < 16 else 3
        for t in self._tiempos.values():
            if t["orden"] == orden:
                self.tiempo.poner(t["id"])
                return
        if self._tiempos:
            self.tiempo.poner(next(iter(self._tiempos)))

    def _cambio_tiempo(self):
        self.mensaje.config(text="")
        self.refrescar()
        self.cedula.focus_set()

    def refrescar(self):
        self._cargar_tiempos()
        fecha = self.fecha.iso()
        tid = self.tiempo.valor()
        self.tabla.limpiar()
        if tid is None:
            return
        precio = self._tiempos[tid]["precio_racion"]
        self.lbl_precio.config(
            text=f"Precio por ración: {fmt_dinero(precio)}" + ("  (configure el precio en «Configuración»)" if not precio else ""))
        filas = raciones.listar(self.con, fecha, tid)
        for f in filas:
            self.tabla.agregar((f["registrado"][11:16], f["cedula"], f["grado"], f["nombres"], f["unidad"],
                                fmt_dinero(f["precio"])), iid=f["id"])
        total = sum(f["precio"] for f in filas)
        self.lbl_total.config(text=f"{self._tiempos[tid]['nombre']}: {len(filas)} raciones · {fmt_dinero(total)}")
        resumen = raciones.resumen_dia(self.con, fecha)
        self.lbl_dia.config(text="Día: " + " · ".join(f"{r['nombre']} {r['cantidad']}" for r in resumen))

    def _contexto(self):
        tid = self.tiempo.valor()
        if tid is None:
            raise ErrorNegocio("Seleccione el tiempo de comida.")
        return self.fecha.iso(), tid

    def _registrar(self, cedula=None):
        cedula = (cedula or self.cedula.get()).strip()
        if not cedula:
            return
        try:
            fecha, tid = self._contexto()
            persona = raciones.registrar(self.con, fecha, tid, cedula)
        except ErrorNegocio as e:
            self.mensaje.config(text=f"✖ {e}", fg=COLOR_ERROR)
            self.bell()
            self.cedula.select_range(0, "end")
            self.cedula.focus_set()
            return
        self.mensaje.config(text=f"✔ {personal.nombre_completo(persona)} — {persona['unidad']}", fg=COLOR_OK)
        self.cedula.delete(0, "end")
        self.refrescar()
        self.cedula.focus_set()

    def _buscar(self):
        self._contexto()
        pid = BuscarPersona(self, self.con, solo_racion=True).mostrar()
        if pid:
            self._registrar(personal.obtener(self.con, pid)["cedula"])

    def _desde_lista(self):
        fecha, tid = self._contexto()
        ids = BuscarPersona(self, self.con, multiple=True, solo_racion=True,
                            titulo=f"Registrar {self._tiempos[tid]['nombre'].lower()} a varias personas").mostrar()
        if not ids:
            return
        registradas, existentes, rechazadas = raciones.registrar_varios(self.con, fecha, tid, ids)
        texto = f"Se registraron {registradas} raciones."
        if existentes:
            texto += f"\n{existentes} personas ya tenían la ración registrada."
        if rechazadas:
            texto += "\n\nNo registradas:\n" + "\n".join(rechazadas[:15])
        messagebox.showinfo("Raciones", texto, parent=self)
        self.refrescar()

    def _quitar(self):
        sel = self.tabla.seleccion()
        if not sel:
            raise ErrorNegocio("Seleccione las raciones que desea quitar.")
        if messagebox.askyesno("Quitar raciones", f"¿Quitar {len(sel)} ración(es) registrada(s)?", parent=self):
            raciones.eliminar(self.con, [int(i) for i in sel])
            self.refrescar()

    def al_mostrar(self):
        self.refrescar()
        self.cedula.focus_set()
