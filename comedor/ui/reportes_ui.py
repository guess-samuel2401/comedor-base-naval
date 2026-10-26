"""Pestaña de reportes."""
import tkinter as tk
from datetime import date, timedelta
from tkinter import ttk

from .. import personal, reportes
from ..util import hoy, primer_dia_mes
from .comun import CampoFecha, VistaReporte

FIRMAS = {
    "Liquidación de raciones (Armada)": ["Administrador del comedor", "Jefe de Abastecimientos", "Visto bueno"],
}


class PestanaReportes(ttk.Frame):
    titulo = "Reportes"

    def __init__(self, padre, app):
        super().__init__(padre, padding=10)
        self.con = app.con
        izq = ttk.Frame(self)
        izq.pack(side="left", fill="y", padx=(0, 12))
        ttk.Label(izq, text="Reporte", style="Subtitulo.TLabel").pack(anchor="w")
        self.lista = tk.Listbox(izq, height=len(reportes.CATALOGO), exportselection=False, activestyle="none",
                                font=("Segoe UI", 10), width=32)
        for nombre, *_ in reportes.CATALOGO:
            self.lista.insert("end", nombre)
        self.lista.pack(anchor="w", pady=4)
        self.lista.selection_set(0)
        self.lista.bind("<<ListboxSelect>>", lambda e: self._cambio())
        self.lista.bind("<Double-1>", lambda e: self._generar())

        p = ttk.LabelFrame(izq, text=" Período ", padding=8)
        p.pack(fill="x", pady=8)
        ttk.Label(p, text="Desde:").grid(row=0, column=0, sticky="e")
        self.desde = CampoFecha(p, iso=primer_dia_mes())
        self.desde.grid(row=0, column=1, sticky="w", padx=4, pady=2)
        ttk.Label(p, text="Hasta:").grid(row=1, column=0, sticky="e")
        self.hasta = CampoFecha(p)
        self.hasta.grid(row=1, column=1, sticky="w", padx=4, pady=2)
        rapidos = ttk.Frame(p)
        rapidos.grid(row=2, column=0, columnspan=2, pady=(6, 0))
        ttk.Button(rapidos, text="Hoy", width=8, command=lambda: self._rango(hoy(), hoy())).pack(side="left")
        ttk.Button(rapidos, text="Este mes", width=9, command=lambda: self._rango(primer_dia_mes(), hoy())).pack(
            side="left", padx=2)
        ttk.Button(rapidos, text="Mes anterior", width=11, command=self._mes_anterior).pack(side="left")

        self.f_unidad = ttk.LabelFrame(izq, text=" Unidad ", padding=8)
        self.f_unidad.pack(fill="x")
        self.unidad = ttk.Combobox(self.f_unidad, state="readonly", width=28)
        self.unidad.pack(fill="x")

        ttk.Button(izq, text="Generar reporte", style="Grande.TButton", command=self._generar).pack(fill="x", pady=12)

        self.vista = VistaReporte(self, self.con)
        self.vista.pack(side="left", fill="both", expand=True)
        self._cambio()

    def _rango(self, desde, hasta):
        self.desde.poner(desde)
        self.hasta.poner(hasta)
        self._generar()

    def _mes_anterior(self):
        fin = date.fromisoformat(primer_dia_mes()) - timedelta(days=1)
        self._rango(fin.replace(day=1).isoformat(), fin.isoformat())

    def _actual(self):
        return reportes.CATALOGO[self.lista.curselection()[0]]

    def _cambio(self):
        _, _, usa_fechas, usa_unidad = self._actual()
        estado = "normal" if usa_fechas else "disabled"
        self.desde.config(state=estado)
        self.hasta.config(state=estado)
        self.unidad.config(state="readonly" if usa_unidad else "disabled")
        self._generar()

    def _generar(self):
        nombre, funcion, _, _ = self._actual()
        unidad = self.unidad.get()
        rep = funcion(self.con, self.desde.iso(), self.hasta.iso(), "" if unidad == "(todas)" else unidad)
        self.vista.mostrar(rep, firmas=FIRMAS.get(nombre, []))

    def al_mostrar(self):
        actual = self.unidad.get() or "(todas)"
        self.unidad["values"] = ["(todas)"] + personal.unidades(self.con)
        self.unidad.set(actual)
        self._generar()
