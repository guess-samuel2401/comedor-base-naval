"""Pestaña de personal."""
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .. import personal
from ..util import fmt_dinero
from .comun import Formulario, Tabla


class PestanaPersonal(ttk.Frame):
    titulo = "Personal"

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
        for texto, comando in (("Descargar plantilla CSV…", self._plantilla), ("Importar desde Excel (CSV)…", self._importar),
                               ("Editar", self._editar), ("Nueva persona", self._nuevo)):
            ttk.Button(barra, text=texto, command=comando).pack(side="right", padx=3)
        self.tabla = Tabla(self, [("cedula", "Cédula", 110), ("grado", "Grado", 140),
                                  ("nombres", "Apellidos y nombres", 280), ("unidad", "Unidad", 170),
                                  ("racion", "Ración Armada", 100, "center"), ("credito", "Crédito", 70, "center"),
                                  ("limite", "Límite", 90, "e"), ("estado", "Estado", 80)],
                           alto=22, al_doble_clic=self._editar)
        self.tabla.pack(fill="both", expand=True, pady=8)
        self.lbl = ttk.Label(self, foreground="#555")
        self.lbl.pack(anchor="w")

    def refrescar(self):
        filas = personal.listar(self.con, self.texto.get().strip(), solo_activos=not self.inactivos.get())
        self.tabla.limpiar()
        for p in filas:
            limite = (fmt_dinero(p["limite_credito"]) if p["limite_credito"] else "Sin límite") if p["credito"] else ""
            self.tabla.agregar((p["cedula"], p["grado"], p["nombres"], p["unidad"],
                                "Sí" if p["racion_institucional"] else "No", "Sí" if p["credito"] else "",
                                limite, "Activo" if p["activo"] else "Inactivo"),
                               iid=p["id"], tags=() if p["activo"] else ("gris",))
        self.lbl.config(text=f"{len(filas)} personas")

    def _formulario(self, personal_id=None):
        valores = dict(personal.obtener(self.con, personal_id)) if personal_id else {
            "racion_institucional": True, "activo": True}
        Formulario(
            self, "Editar persona" if personal_id else "Nueva persona",
            [("cedula", "Cédula / N° identificación", "texto"), ("grado", "Grado", "lista", personal.GRADOS),
             ("nombres", "Apellidos y nombres", "texto"),
             ("unidad", "Unidad / departamento", "lista", personal.unidades(self.con)),
             ("racion_institucional", "Ración pagada por la Armada", "check"),
             ("credito", "Autorizado a consumir a crédito", "check"),
             ("limite_credito", "Límite de crédito mensual (0 = sin límite)", "dinero"),
             ("activo", "Activo (desmarque si salió de la base)", "check")],
            valores, al_guardar=lambda d: personal.guardar(self.con, d, personal_id),
        ).mostrar()
        self.refrescar()

    def _nuevo(self):
        self._formulario()

    def _editar(self):
        self._formulario(int(self.tabla.requerir("una persona")))

    def _importar(self):
        ruta = filedialog.askopenfilename(parent=self, title="Importar personal",
                                          filetypes=[("CSV", "*.csv"), ("Texto", "*.txt"), ("Todos", "*.*")])
        if not ruta:
            return
        nuevos, actualizados, errores = personal.importar_csv(self.con, ruta)
        texto = f"Personas nuevas: {nuevos}\nActualizadas: {actualizados}"
        if errores:
            texto += f"\n\nCon errores ({len(errores)}):\n" + "\n".join(errores[:20])
        messagebox.showinfo("Importación terminada", texto, parent=self)
        self.refrescar()

    def _plantilla(self):
        ruta = filedialog.asksaveasfilename(parent=self, title="Guardar plantilla", defaultextension=".csv",
                                            initialfile="plantilla_personal.csv", filetypes=[("CSV", "*.csv")])
        if ruta:
            with open(ruta, "w", encoding="utf-8-sig", newline="") as f:
                f.write(personal.PLANTILLA_CSV)
            messagebox.showinfo("Plantilla", "Abra la plantilla en Excel, llene una fila por persona y "
                                             "guárdela como CSV. Luego use «Importar desde Excel (CSV)».", parent=self)

    def al_mostrar(self):
        self.refrescar()
