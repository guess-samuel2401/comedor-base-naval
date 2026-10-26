"""Ventana principal del sistema."""
import traceback
import tkinter as tk
from datetime import datetime
from tkinter import font, messagebox, ttk

from .. import __version__, db
from ..util import ErrorNegocio, fecha_ver, hoy
from .bodega_ui import PestanaBodega
from .caja_ui import PestanaCaja
from .config_ui import PestanaConfig
from .creditos_ui import PestanaCreditos
from .personal_ui import PestanaPersonal
from .productos_ui import PestanaProductos
from .raciones_ui import PestanaRaciones
from .reportes_ui import PestanaReportes

PESTANAS = (PestanaRaciones, PestanaCaja, PestanaCreditos, PestanaBodega, PestanaPersonal, PestanaProductos,
            PestanaReportes, PestanaConfig)


class Aplicacion(tk.Tk):
    def __init__(self, con):
        super().__init__()
        self.con = con
        self.geometry("1280x760")
        self.minsize(1100, 640)
        icono = db.RECURSOS / "comedor.ico"
        if icono.exists():
            self.iconbitmap(default=str(icono))
        self._estilos()
        self.report_callback_exception = self._error

        cab = ttk.Frame(self, padding=(14, 8), style="Cabecera.TFrame")
        cab.pack(fill="x")
        self.lbl_nombre = ttk.Label(cab, style="Cabecera.TLabel")
        self.lbl_nombre.pack(side="left")
        self.lbl_fecha = ttk.Label(cab, style="CabeceraSub.TLabel")
        self.lbl_fecha.pack(side="right")
        self.actualizar_encabezado()

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)
        self.pestanas = []
        for clase in PESTANAS:
            pestana = clase(self.notebook, self)
            self.notebook.add(pestana, text=f"  {pestana.titulo}  ")
            self.pestanas.append(pestana)
        self.notebook.bind("<<NotebookTabChanged>>", lambda e: self._al_cambiar())
        self.after(50, self._al_cambiar)

    def _estilos(self):
        estilo = ttk.Style(self)
        if "vista" in estilo.theme_names():
            estilo.theme_use("vista")
        for nombre in ("TkDefaultFont", "TkTextFont", "TkHeadingFont", "TkMenuFont"):
            font.nametofont(nombre).configure(family="Segoe UI", size=10)
        alto_fila = font.nametofont("TkDefaultFont").metrics("linespace") + 8
        estilo.configure("Treeview", rowheight=alto_fila)
        estilo.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        estilo.configure("TNotebook.Tab", padding=(10, 5))
        estilo.configure("Grande.TButton", font=("Segoe UI", 11, "bold"))
        estilo.configure("Subtitulo.TLabel", font=("Segoe UI", 11, "bold"))
        estilo.configure("Cabecera.TFrame", background="#0b2e4f")
        estilo.configure("Cabecera.TLabel", background="#0b2e4f", foreground="white", font=("Segoe UI", 15, "bold"))
        estilo.configure("CabeceraSub.TLabel", background="#0b2e4f", foreground="#cfe0f0", font=("Segoe UI", 10))

    def actualizar_encabezado(self):
        enc = db.encabezado(self.con)
        self.title(f"{enc['nombre_comedor']} – Facturación y costos")
        self.lbl_nombre.config(text=f"⚓  {enc['nombre_comedor']}  ·  {enc['entidad']}")
        self.lbl_fecha.config(text=f"Hoy: {fecha_ver(hoy())}   ·   v{__version__}")

    def _al_cambiar(self):
        pestana = self.nametowidget(self.notebook.select())
        if hasattr(pestana, "al_mostrar"):
            pestana.al_mostrar()

    def _ventana_activa(self):
        try:
            widget = self.focus_get()
            return widget.winfo_toplevel() if widget else self
        except (KeyError, tk.TclError):
            return self

    def _error(self, tipo, valor, tb):
        padre = self._ventana_activa()
        if isinstance(valor, ErrorNegocio):
            messagebox.showwarning("Atención", str(valor), parent=padre)
            return
        detalle = "".join(traceback.format_exception(tipo, valor, tb))
        try:
            with open(db.RUTA_DB.parent / "errores.log", "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}]\n{detalle}")
        except OSError:
            pass
        messagebox.showerror("Error inesperado", f"{tipo.__name__}: {valor}\n\n"
                                                 f"El detalle se guardó en datos\\errores.log.", parent=padre)


def main():
    try:  # textos nítidos en pantallas con escala de Windows, e ícono propio en la barra de tareas
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ComedorBaseNaval.Facturacion")
    except Exception:
        pass
    con = db.conectar()
    try:
        Aplicacion(con).mainloop()
    finally:
        con.close()
