"""Pestaña de créditos: saldos del personal, cobros y estados de cuenta."""
import tkinter as tk
from datetime import date
from tkinter import ttk

from .. import personal, reportes, ventas
from ..util import fmt_dinero, hoy, primer_dia_mes
from .comun import CampoFecha, Dialogo, Formulario, Tabla, VistaReporte

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]


class PestanaCreditos(ttk.Frame):
    titulo = "Créditos"

    def __init__(self, padre, app):
        super().__init__(padre, padding=10)
        self.app = app
        self.con = app.con
        barra = ttk.Frame(self)
        barra.pack(fill="x")
        ttk.Label(barra, text="Buscar:").pack(side="left")
        self.texto = ttk.Entry(barra, width=30)
        self.texto.pack(side="left", padx=6)
        self.texto.bind("<KeyRelease>", lambda e: self.refrescar())
        self.solo_saldo = tk.BooleanVar(value=True)
        ttk.Checkbutton(barra, text="Solo con saldo pendiente", variable=self.solo_saldo,
                        command=self.refrescar).pack(side="left", padx=10)
        ttk.Button(barra, text="Estado de cuenta…", command=self._estado).pack(side="right")
        ttk.Button(barra, text="Registrar cobro…", command=self._cobro).pack(side="right", padx=6)

        self.tabla = Tabla(self, [("cedula", "Cédula", 110), ("grado", "Grado", 130),
                                  ("nombres", "Apellidos y nombres", 260), ("unidad", "Unidad", 160),
                                  ("limite", "Límite", 90, "e"), ("cargos", "Consumos", 100, "e"),
                                  ("abonos", "Pagos", 100, "e"), ("saldo", "Saldo", 110, "e")],
                           alto=20, al_doble_clic=self._estado)
        self.tabla.pack(fill="both", expand=True, pady=8)
        pie = ttk.Frame(self)
        pie.pack(fill="x")
        ttk.Label(pie, text="Para autorizar crédito a una persona, edítela en la pestaña «Personal».",
                  foreground="#555").pack(side="left")
        self.lbl_total = ttk.Label(pie, style="Subtitulo.TLabel")
        self.lbl_total.pack(side="right")

    def refrescar(self):
        texto = self.texto.get().strip().lower()
        self.tabla.limpiar()
        total = 0
        for s in ventas.saldos_credito(self.con):
            if self.solo_saldo.get() and s["saldo"] <= 0:
                continue
            if texto and texto not in f"{s['cedula']} {s['nombres']} {s['unidad']} {s['grado']}".lower():
                continue
            total += s["saldo"]
            self.tabla.agregar((s["cedula"], s["grado"], s["nombres"], s["unidad"],
                                fmt_dinero(s["limite_credito"]) if s["limite_credito"] else "Sin límite",
                                fmt_dinero(s["cargos"]), fmt_dinero(s["abonos"]), fmt_dinero(s["saldo"])),
                               iid=s["id"], tags=() if s["credito"] else ("gris",))
        self.lbl_total.config(text=f"Total por cobrar: {fmt_dinero(total)}")

    def _cobro(self):
        pid = int(self.tabla.requerir("una persona"))
        persona = personal.obtener(self.con, pid)
        saldo = ventas.saldo_credito(self.con, pid)
        mes = MESES[date.today().month - 1]
        Formulario(
            self, f"Registrar cobro – {personal.nombre_completo(persona)}",
            [("fecha", "Fecha", "fecha"), ("monto", "Monto cobrado", "dinero"), ("detalle", "Detalle", "texto")],
            {"monto": saldo, "detalle": f"Descuento rol {mes}"},
            al_guardar=lambda d: ventas.registrar_cobro(self.con, pid, d["monto"], d["detalle"], d["fecha"]),
            nota=f"Saldo pendiente: {fmt_dinero(saldo)}",
        ).mostrar()
        self.refrescar()

    def _estado(self):
        pid = int(self.tabla.requerir("una persona"))
        EstadoCuenta(self, self.con, pid).mostrar()

    def al_mostrar(self):
        self.refrescar()


class EstadoCuenta(Dialogo):
    def __init__(self, padre, con, personal_id):
        super().__init__(padre, "Estado de cuenta", redimensionable=True)
        self.con = con
        self.personal_id = personal_id
        barra = ttk.Frame(self.cuerpo)
        barra.pack(fill="x")
        ttk.Label(barra, text="Desde:").pack(side="left")
        self.desde = CampoFecha(barra, iso=primer_dia_mes())
        self.desde.pack(side="left", padx=4)
        ttk.Label(barra, text="Hasta:").pack(side="left", padx=(8, 0))
        self.hasta = CampoFecha(barra, iso=hoy())
        self.hasta.pack(side="left", padx=4)
        ttk.Button(barra, text="Generar", command=self._generar).pack(side="left", padx=8)
        persona = personal.obtener(con, personal_id)
        self.vista = VistaReporte(self.cuerpo, con, firmas=["Administrador del comedor",
                                                            personal.nombre_completo(persona)])
        self.vista.pack(fill="both", expand=True, pady=(8, 0))
        self._generar()

    def _generar(self):
        self.vista.mostrar(reportes.estado_cuenta(self.con, self.personal_id, self.desde.iso(), self.hasta.iso()))
